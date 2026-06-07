import math
import random
import pygame
from typing import Tuple, Optional, List

from Choi_animals import CHOI_IMAGE_CACHE
from animal import Animal, Predator, Prey, Egg, TILE_SIZE


# ════════════════════════════════════════════════
#  Anaconda
# ════════════════════════════════════════════════
Bae = {}
class Anaconda(Predator):
    """
    아나콘다 클래스.

    행동 흐름:
      [물속] idle(자유이동) → waiting(발견·정지) → rushing(기습)
          기습 성공 → choke + eat
          기습 실패 → chasing(추격)
      [육지] 최대속도·가속도·스태미나 감소 패널티
    """

    SPECIES_VISION_RANGE: float = 200.0
    SPECIES_VISION_ANGLE: float = 130.0

    # 행동 상태 상수
    _STATE_IDLE    = "idle"
    _STATE_WAITING = "waiting"
    _STATE_RUSHING = "rushing"
    _STATE_CHASING = "chasing"

    def __init__(
        self,
        name: str,
        coordinate: Tuple[float, float],
        choke_range: float = 35.0,
        ambush_wait_time: float = 2.0,
        # 물속 스탯
        water_max_speed: float = 120.0,
        water_max_accelerate: float = 260.0,
        # 육지 스탯 (패널티)
        land_max_speed: float = 55.0,
        land_max_accelerate: float = 110.0,
        land_stamina_drain: float = 6.0,   # 육지에서 초당 스태미나 감소
        **kwargs,
    ):
        super().__init__(
            name=name,
            coordinate=coordinate,
            attack_range=35.0,
            hunt_range=220.0,
            attack_success_rate=0.55,
            hunger_limit=40.0,
            chase_speed_mul=1.3,
            max_speed=water_max_speed,
            max_accelerate=water_max_accelerate,
            **kwargs,
        )

        # 💡 1. 여기서 코뿔소 전용 이미지를 설정
        self.image_path = "anaconda.png"  # 아나콘다 이미지 파일명
        self.image = None
        
        # 이미지가 캐시에 없으면 최초 1회 로드
        if self.image_path not in Bae:
            try:
                loaded_img = pygame.image.load(self.image_path).convert_alpha()
                Bae[self.image_path] = loaded_img
            except Exception as e:
                print(f"⚠️ {name} 이미지 로드 실패: {e}")
                # 💡 [핵심] 실패하더라도 딕셔너리에 None을 넣어줘야함
                Bae[self.image_path] = None
        orig_img = Bae[self.image_path]
        orig_w, orig_h = orig_img.get_size() # 원본 이미지의 가로, 세로 픽셀
            
        # 동물의 크기(size)를 기준으로 최대 렌더링 크기 설정
        target_max_size = int(self.size * 2.5)
            
        # 가로와 세로 중 더 긴 쪽을 기준으로 축소/확대 비율(scale_factor)을 계산
        scale_factor = target_max_size / max(orig_w, orig_h)
            
        # 구한 비율을 가로, 세로에 똑같이 곱해주어 비율 유지
        new_w = int(orig_w * scale_factor)
        new_h = int(orig_h * scale_factor)
            
        # 새로운 가로, 세로 크기로 스케일링
        self.image = pygame.transform.scale(orig_img, (new_w, new_h))

        # ── 아나콘다 전용 속성 ──
        self.choke_range: float = choke_range
        self.hidden: bool = False

        # 물속/육지 스탯
        self.water_max_speed     = water_max_speed
        self.water_max_accelerate = water_max_accelerate
        self.land_max_speed      = land_max_speed
        self.land_max_accelerate = land_max_accelerate
        self.land_stamina_drain  = land_stamina_drain

        # 매복 상태
        self._state: str = self._STATE_IDLE
        self._ambush_timer: float = 0.0
        self._ambush_wait_time: float = ambush_wait_time
        self._ambush_rush_speed: float = 2.5
        self._target: Optional[Animal] = None

    # ── 은신 ────────────────────────────────────

    def hide(self):
        self.hidden = True

    def stop_hide(self):
        self.hidden = False

    # ── 조르기 ───────────────────────────────────

    def choke(self, target: Animal, dt: float,
              choke_dps: float = 15.0,
              stun_duration: float = 0.5):
        """choke_range 이내 대상 조르기: 지속 피해 + 스턴."""
        if not target.alive:
            return
        if self.distance_to(target) <= self.choke_range:
            target.take_damage(choke_dps * dt, source=f"{self.name}_choke")
            target.apply_stun(stun_duration)

    HUNT_TARGETS    = {"Capybara", "Monkey", "Parrot", "ToxicFrog"}
    HATCH_TIME      = 90.0   # 아나콘다 알 부화 시간 (초)
    WATER_PREY_RANGE = 160.0  # 피식자 주변 이 거리 이내에 물이 있어야 타겟으로 삼음

    # ── 물 관련 유틸 ─────────────────────────────

    def _is_water_tile(self, wx: float, wy: float, game_map) -> bool:
        """world 좌표 (wx, wy)가 물 타일인지 확인."""
        tx, ty = int(wx // TILE_SIZE), int(wy // TILE_SIZE)
        return game_map.is_water(tx, ty)

    def _prey_near_water(self, prey: Animal, game_map) -> bool:
        """
        피식자 주변 WATER_PREY_RANGE 이내에 물 타일이 있는지 확인.
        반지름을 TILE_SIZE 간격으로 샘플링.
        """
        px, py = prey.coordinate
        r = self.WATER_PREY_RANGE
        step = TILE_SIZE
        steps = int(r / step)
        for dx in range(-steps, steps + 1):
            for dy in range(-steps, steps + 1):
                wx = px + dx * step
                wy = py + dy * step
                if self._is_water_tile(wx, wy, game_map):
                    return True
        return False

    def _nearest_water_point_to(self, target_coord: Tuple[float, float],
                                 game_map) -> Optional[Tuple[float, float]]:
        """
        자신의 현재 위치에서 탐색 가능한 물 타일 중
        target_coord에 가장 가까운 타일의 중심 좌표 반환.
        hunt_range 내 물 타일만 탐색.
        """
        ox, oy = self.coordinate
        tx, ty = target_coord
        search_r = self.hunt_range
        step = TILE_SIZE
        steps = int(search_r / step)

        best_point = None
        best_dist  = float('inf')

        for dx in range(-steps, steps + 1):
            for dy in range(-steps, steps + 1):
                wx = ox + dx * step
                wy = oy + dy * step
                if not self._is_water_tile(wx, wy, game_map):
                    continue
                dist_to_target = math.hypot(wx - tx, wy - ty)
                if dist_to_target < best_dist:
                    best_dist  = dist_to_target
                    best_point = (wx + TILE_SIZE / 2, wy + TILE_SIZE / 2)

        return best_point

    # ── 기습 성공 확률 계산 ──────────────────────

    def _calc_ambush_success_rate(self, target: Animal) -> float:
        """
        기습 성공 확률.
        아나콘다가 배고플수록, 피식자의 HP/스태미나가 낮을수록 성공률 상승.
        """
        base = 0.55
        # 아나콘다 배고픔 보너스 (hunger 100 → +0.20)
        hunger_bonus = (self.hunger / 100.0) * 0.20
        # 피식자 상태 보너스
        prey_hp_bonus      = (1.0 - target.hp / target.max_hp) * 0.10
        prey_stamina_bonus = (1.0 - target.stamina / target.max_stamina) * 0.10
        # 아나콘다 자신의 스태미나가 낮으면 성공률 감소
        self_stamina_penalty = (1.0 - self.stamina / self.max_stamina) * 0.15
        rate = base + hunger_bonus + prey_hp_bonus + prey_stamina_bonus - self_stamina_penalty
        return max(0.05, min(0.95, rate))

    # ── 환경별 스탯 적용 ────────────────────────

    def _apply_environment_stats(self, game_map):
        """현재 타일 위치로 environment_status 갱신 후 이동 스탯 적용."""
        tx = int(self.coordinate[0] // TILE_SIZE)
        ty = int(self.coordinate[1] // TILE_SIZE)
        if game_map.is_water(tx, ty):
            self.environment_status = "water"
            self.max_speed      = self.water_max_speed
            self.max_accelerate = self.water_max_accelerate
        else:
            self.environment_status = "land"
            self.max_speed      = self.land_max_speed
            self.max_accelerate = self.land_max_accelerate

    def _apply_land_stamina_drain(self, dt: float):
        """육지에 있으면 스태미나 지속 감소."""
        if self.environment_status != "water":
            self.stamina = max(0.0, self.stamina - self.land_stamina_drain * dt)

    # ── 상태 전환 헬퍼 ──────────────────────────

    def _set_state(self, state: str, target: Optional[Animal] = None):
        self._state = state
        self._ambush_timer = 0.0
        self._target = target
        if state != self._STATE_WAITING:
            pass  # waiting 외엔 정지 안 함

    # ── 행동 FSM ────────────────────────────────

    def _update_behavior(self, dt: float, animals: List[Animal], game_map):
        state = self._state

        # ── idle: 물속 이동, 물가 피식자 탐색 ──
        if state == self._STATE_IDLE:
            self.hide()
            if self.hunger < self.hunger_limit:
                self.move(dt)   # 배부르면 자유 이동
                return

            # 물 근처에 있는 피식자만 타겟
            prey_list = [
                a for a in animals
                if self._is_prey(a) and a.alive
                and self.distance_to(a) <= self.hunt_range
                and self.can_see(a, game_map)
                and self._prey_near_water(a, game_map)
            ]
            if not prey_list:
                self.move(dt)
                return

            closest = min(prey_list, key=lambda a: self.distance_to(a))

            # 물속에서 피식자에게 최대한 접근 (물 타일 중 피식자와 가장 가까운 점)
            approach = self._nearest_water_point_to(closest.coordinate, game_map)
            if approach and self.distance_to(approach) > self.attack_range:
                # 아직 물속 접근 중
                self.move(dt, approach)
            else:
                # 충분히 접근됨 → 정지 후 기습 대기
                self._set_state(self._STATE_WAITING, closest)
                self.stop()

        # ── waiting: 정지 후 기습 카운트다운 ──
        elif state == self._STATE_WAITING:
            self.stop()
            t = self._target
            if t is None or not t.alive:
                self._set_state(self._STATE_IDLE)
                return
            # 피식자가 물가를 벗어나면 포기
            if not self._prey_near_water(t, game_map):
                self._set_state(self._STATE_IDLE)
                return
            self._ambush_timer += dt
            if self._ambush_timer >= self._ambush_wait_time:
                self._set_state(self._STATE_RUSHING, t)

        # ── rushing: 기습 돌진 ──
        elif state == self._STATE_RUSHING:
            t = self._target
            if t is None or not t.alive:
                self._set_state(self._STATE_IDLE)
                self.stop_hide()
                return

            self.stop_hide()
            self.move(dt, t.coordinate, self._ambush_rush_speed)

            if self.distance_to(t) <= self.attack_range:
                success_rate = self._calc_ambush_success_rate(t)
                if random.random() < success_rate:
                    # 기습 성공 → choke + 처치
                    self.choke(t, dt)
                    self.attack(t, base_damage=30.0)
                    if not t.alive:
                        self.eat(45.0)
                        self._set_state(self._STATE_IDLE)
                else:
                    # 기습 실패 → 추격 전환
                    print(f"{self.name} 기습 실패 → 추격 시작")
                    self._set_state(self._STATE_CHASING, t)

            # 너무 멀어지면 포기
            if self.distance_to(t) > self.hunt_range * 1.5:
                self._set_state(self._STATE_IDLE)

        # ── chasing: 기습 실패 후 추격 ──
        elif state == self._STATE_CHASING:
            t = self._target
            if t is None or not t.alive:
                self._set_state(self._STATE_IDLE)
                return
            if not self.can_see(t, game_map):
                self._set_state(self._STATE_IDLE)
                return

            self.move(dt, t.coordinate, self.chase_speed_mul)
            self.use_stamina(8.0 * dt)
            self.choke(t, dt)

            if self.distance_to(t) <= self.attack_range:
                if random.random() < self.attack_success_rate:
                    self.attack(t, base_damage=25.0)
                    if not t.alive:
                        self.eat(40.0)
                        self._set_state(self._STATE_IDLE)

            # 너무 멀어지거나 스태미나 소진 시 포기
            if (self.distance_to(t) > self.hunt_range * 1.5
                    or self.stamina <= 0):
                self._set_state(self._STATE_IDLE)

    # ── 업데이트 ─────────────────────────────────

    def update(self, dt: float, game_map, weather, animals: List[Animal]):
        super().update(dt, game_map, weather, animals)
        if not self.alive:
            return

        self._apply_environment_stats(game_map)
        self._apply_land_stamina_drain(dt)

        # 물속일 때만 매복 FSM 작동
        # 육지에서는 Predator 기본 사냥 + 은신 해제
        if self.environment_status == "water":
            self.stop_hunt()   # Predator 기본 사냥 비활성화
            self._update_behavior(dt, animals, game_map)
        else:
            if self.hidden:
                self.stop_hide()
            # 육지 추격 중이면 계속 추격
            if self._state == self._STATE_CHASING:
                self._update_behavior(dt, animals, game_map)

    # ── 번식 ────────────────────────────────────

    def make_child(self) -> "Egg":
        return Egg(
            coordinate=self.home_coordinate or tuple(self.coordinate),
            parent=self,
            hatch_time=self.HATCH_TIME,
        )

    def _spawn_child(self) -> "Anaconda":
        """Egg.update()에서 부화 시 호출되는 실제 자식 생성 메서드."""
        return Anaconda(
            name=f"Anaconda_{random.randint(1000, 9999)}",
            coordinate=tuple(self.coordinate),
        )

    # ── 렌더링 ──────────────────────────────────

    def draw(self, screen: pygame.Surface, camera):
        if not self.alive:
            return
        sx, sy = camera.world_to_screen(self.coordinate[0], self.coordinate[1])

        body_color = (10, 50, 10) if self.hidden else (30, 110, 30)
        pygame.draw.ellipse(screen, body_color,
                            (int(sx) - 14, int(sy) - 7, 28, 14))

        bw = 28
        bx, by = int(sx) - bw // 2, int(sy) - 16
        pygame.draw.rect(screen, (80, 0, 0),   (bx, by, bw, 3))
        pygame.draw.rect(screen, (0, 200, 60),
                         (bx, by, int(bw * self.hp / self.max_hp), 3))

        if self.is_stunned:
            pygame.draw.circle(screen, (255, 255, 0),   (int(sx) + 12, int(sy) - 12), 3)
        if self.is_poisoned:
            pygame.draw.circle(screen, (100, 255, 100), (int(sx) - 12, int(sy) - 12), 3)
        if self.hidden:
            pygame.draw.ellipse(screen, (0, 180, 0),
                                (int(sx) - 16, int(sy) - 9, 32, 18), 1)

    def __repr__(self):
        return (f"<Anaconda '{self.name}' hp={self.hp}/{self.max_hp} ")
                

def _is_water(game_map, tx, ty):
    t = game_map.get_tile(tx, ty)
    return t in _WATER_TILES

def _find_shore_positions(game_map, cx, cy, search_radius_tiles=20, max_candidates=12):
    origin_tx = int(cx // TILE_SIZE)
    origin_ty = int(cy // TILE_SIZE)
    candidates = []
    for dy in range(-search_radius_tiles, search_radius_tiles + 1):
        for dx in range(-search_radius_tiles, search_radius_tiles + 1):
            tx, ty = origin_tx + dx, origin_ty + dy
            if not _is_water(game_map, tx, ty):
                continue
            if any(not _is_water(game_map, tx + ndx, ty + ndy)
                   for ndx, ndy in ((1,0),(-1,0),(0,1),(0,-1))):
                px = (tx + 0.5) * TILE_SIZE
                py = (ty + 0.5) * TILE_SIZE
                dist = math.hypot(px - cx, py - cy)
                candidates.append((dist, px, py))
    candidates.sort()
    return [(px, py) for _, px, py in candidates[:max_candidates]]


import random
import math
import pygame
from typing import Tuple, Optional, List

from animal import Animal, Predator, Prey
from map_system import TileType, TILE_SIZE

_WATER_TILES = (TileType.WATER, TileType.DEEP_WATER)

def _is_water(game_map, tx, ty):
    t = game_map.get_tile(tx, ty)
    return t in _WATER_TILES

def _find_shore_positions(game_map, cx, cy, search_radius_tiles=20, max_candidates=12):
    origin_tx = int(cx // TILE_SIZE)
    origin_ty = int(cy // TILE_SIZE)
    candidates = []
    for dy in range(-search_radius_tiles, search_radius_tiles + 1):
        for dx in range(-search_radius_tiles, search_radius_tiles + 1):
            tx, ty = origin_tx + dx, origin_ty + dy
            if not _is_water(game_map, tx, ty):
                continue
            if any(not _is_water(game_map, tx + ndx, ty + ndy)
                   for ndx, ndy in ((1,0),(-1,0),(0,1),(0,-1))):
                px = (tx + 0.5) * TILE_SIZE
                py = (ty + 0.5) * TILE_SIZE
                dist = math.hypot(px - cx, py - cy)
                candidates.append((dist, px, py))
    candidates.sort()
    return [(px, py) for _, px, py in candidates[:max_candidates]]


class Crocodile(Predator):
    """
    악어.
    idle(유영) -> seeking_shore(물가 이동) -> lurking(잠복) -> rushing(기습)
      -> death_roll(데스롤) -> idle
      -> chasing(추격) -> idle
    """
    SPECIES_VISION_RANGE = 230.0
    SPECIES_VISION_ANGLE = 110.0
    minimap_color = (0, 200, 200)

    _IDLE          = "idle"
    _SEEKING_SHORE = "seeking_shore"
    _LURKING       = "lurking"
    _RUSHING       = "rushing"
    _DEATH_ROLL    = "death_roll"
    _CHASING       = "chasing"

    def __init__(self, name, coordinate,
                 water_max_speed=120.0, water_max_accel=260.0,
                 rush_max_speed=200.0, rush_max_accel=450.0,
                 land_stamina_drain=12.0,
                 drink_range=160.0, lurk_timeout=30.0,
                 death_roll_dps=35.0, death_roll_duration=2.5,
                 **kwargs):
        super().__init__(
            name=name, coordinate=coordinate,
            attack_range=45.0, hunt_range=260.0,
            attack_success_rate=0.60, hunger_limit=45.0, chase_speed_mul=1.4,
            max_speed=water_max_speed, max_accelerate=water_max_accel,
            hp=200, max_hp=200, max_stamina=130.0, stamina=130.0,
            environment_status="water",
            **kwargs,
        )
        self.water_max_speed    = water_max_speed
        self.water_max_accel    = water_max_accel
        self.rush_max_speed     = rush_max_speed
        self.rush_max_accel     = rush_max_accel
        self.land_stamina_drain = land_stamina_drain
        self.drink_range        = drink_range
        self.lurk_timeout       = lurk_timeout
        self.death_roll_dps     = death_roll_dps
        self.death_roll_duration = death_roll_duration

        self.submerged  = False
        self._state     = self._IDLE
        self._target    = None
        self._shore_pos = None
        self._lurk_timer = 0.0
        self._roll_timer = 0.0

    def _set_state(self, state, target=None):
        self._state      = state
        self._target     = target
        self._roll_timer = 0.0
        self._lurk_timer = 0.0
        if state not in (self._LURKING, self._SEEKING_SHORE):
            self.submerged = False
        if state == self._RUSHING:
            self.max_speed      = self.rush_max_speed
            self.max_accelerate = self.rush_max_accel
        else:
            self.max_speed      = self.water_max_speed
            self.max_accelerate = self.water_max_accel

    def _pick_shore(self, game_map):
        shores = _find_shore_positions(game_map, self.coordinate[0], self.coordinate[1])
        return shores[0] if shores else None

    def _do_death_roll(self, target, dt):
        self._roll_timer += dt
        if target.alive:
            target.take_damage(self.death_roll_dps * dt,
                               source=f"{self.name}_death_roll")
            target.apply_stun(0.3)
        return self._roll_timer >= self.death_roll_duration

    def _ambush_rate(self, target):
        base = 0.65
        b  = 0.15 if self.submerged else 0.0
        b += (self.hunger / 100.0) * 0.10
        b += (1.0 - target.hp / target.max_hp) * 0.10
        b -= (1.0 - self.stamina / self.max_stamina) * 0.15
        return max(0.05, min(0.95, base + b))

    def _apply_land_drain(self, dt):
        if self.environment_status != "water":
            if math.hypot(*self.velocity) > 5.0:
                self.stamina = max(0.0, self.stamina - self.land_stamina_drain * dt)

    def _update_behavior(self, dt, animals, game_map):
        s = self._state

        if s == self._IDLE:
            self.submerged = False
            self.move(dt)
            if self.hunger >= self.hunger_limit:
                shore = self._pick_shore(game_map)
                if shore:
                    self._shore_pos = shore
                    self._set_state(self._SEEKING_SHORE)

        elif s == self._SEEKING_SHORE:
            if self._shore_pos is None:
                self._set_state(self._IDLE); return
            self.move(dt, self._shore_pos)
            if self.distance_to(self._shore_pos) < TILE_SIZE:
                self.stop()
                self.submerged = True
                self._set_state(self._LURKING)
            if self.hunger < self.hunger_limit * 0.5:
                self._set_state(self._IDLE)

        elif s == self._LURKING:
            self.stop()
            self.submerged = True
            self._lurk_timer += dt
            nearby = [a for a in animals
                      if isinstance(a, Prey) and a.alive
                      and self.distance_to(a) <= self.drink_range]
            if nearby:
                t = min(nearby, key=lambda a: self.distance_to(a))
                self._set_state(self._RUSHING, t); return
            if self.hunger < self.hunger_limit * 0.5:
                self._set_state(self._IDLE)
            elif self._lurk_timer >= self.lurk_timeout:
                shore = self._pick_shore(game_map)
                if shore and shore != self._shore_pos:
                    self._shore_pos = shore
                    self._set_state(self._SEEKING_SHORE)
                else:
                    self._set_state(self._IDLE)

        elif s == self._RUSHING:
            t = self._target
            if t is None or not t.alive:
                self._set_state(self._IDLE); return
            self.move(dt, t.coordinate, 1.0)
            if self.distance_to(t) <= self.attack_range:
                if random.random() < self._ambush_rate(t):
                    self._set_state(self._DEATH_ROLL, t)
                else:
                    print(f"{self.name} 기습 실패 -> 추격")
                    self._set_state(self._CHASING, t)
                return
            if self.distance_to(t) > self.hunt_range:
                self._set_state(self._IDLE)

        elif s == self._DEATH_ROLL:
            t = self._target
            if t is None:
                self._set_state(self._IDLE); return
            self.stop()
            done = self._do_death_roll(t, dt)
            if not t.alive:
                self.eat(55.0)
                self._set_state(self._IDLE)
            elif done:
                self._set_state(self._CHASING, t)

        elif s == self._CHASING:
            t = self._target
            if t is None or not t.alive:
                self._set_state(self._IDLE); return
            if not self.can_see(t, game_map):
                self._set_state(self._IDLE); return
            self.move(dt, t.coordinate, self.chase_speed_mul)
            self.use_stamina(12.0 * dt)
            if self.distance_to(t) <= self.attack_range:
                if random.random() < self.attack_success_rate:
                    self.attack(t, base_damage=40.0)
                    if not t.alive:
                        self.eat(50.0)
                        self._set_state(self._IDLE)
            if self.distance_to(t) > self.hunt_range or self.stamina <= 0:
                self._set_state(self._IDLE)

    def update(self, dt, game_map, weather, animals):
        super().update(dt, game_map, weather, animals)
        if not self.alive:
            return
        self.stop_hunt()
        self._apply_land_drain(dt)
        if (self.environment_status != "water"
                and self._state == self._LURKING):
            self._set_state(self._IDLE)
        self._update_behavior(dt, animals, game_map)

    def make_child(self):
        return Crocodile(
            name=f"Crocodile_{random.randint(1000,9999)}",
            coordinate=tuple(self.coordinate),
        )

    def draw(self, screen, camera):
        if not self.alive:
            return
        sx, sy = camera.world_to_screen(self.coordinate[0], self.coordinate[1])

        if self._state == self._DEATH_ROLL:
            body = (160, 40, 20)
        elif self.submerged:
            body = (15, 35, 15)
        elif self._state in (self._RUSHING, self._CHASING):
            body = (80, 130, 40)
        else:
            body = (55, 100, 45)

        pygame.draw.ellipse(screen, body,
                            (int(sx)-18, int(sy)-8, 36, 16))
        hx = int(sx + math.cos(self.facing_angle) * 16)
        hy = int(sy + math.sin(self.facing_angle) * 16)
        pygame.draw.circle(screen, body, (hx, hy), 7)

        if self._state == self._DEATH_ROLL:
            pygame.draw.circle(screen, (200, 80, 40), (int(sx), int(sy)), 24, 2)
        if self.submerged:
            pygame.draw.ellipse(screen, (30, 140, 160),
                                (int(sx)-20, int(sy)-10, 40, 20), 1)

        bw = 32
        bx, by = int(sx) - bw//2, int(sy) - 20
        pygame.draw.rect(screen, (80,0,0),    (bx, by, bw, 3))
        pygame.draw.rect(screen, (0,200,60),
                         (bx, by, int(bw * self.hp / self.max_hp), 3))
        if self.is_stunned:
            pygame.draw.circle(screen, (255,255,0),   (int(sx)+14, int(sy)-14), 3)
        if self.is_poisoned:
            pygame.draw.circle(screen, (100,255,100), (int(sx)-14, int(sy)-14), 3)

    def __repr__(self):
        return (f"<Crocodile '{self.name}' hp={self.hp}/{self.max_hp} "
                f"state={self._state} submerged={self.submerged} "
                f"hunger={self.hunger:.0f} "
                f"pos=({self.coordinate[0]:.0f},{self.coordinate[1]:.0f})>")

