import math
import random
import pygame
from typing import Tuple, Optional, List

from animal import Animal, Predator, Prey, Egg
from map_system import TileType, TILE_SIZE

Bae={}


# ════════════════════════════════════════════════
#  물 관련 모듈 레벨 유틸 (Crocodile 등에서 공용 사용)
# ════════════════════════════════════════════════

_WATER_TILES = (TileType.WATER, TileType.DEEP_WATER)


def _is_water(game_map, tx: int, ty: int) -> bool:
    """타일 좌표 (tx, ty)가 물 타일인지 확인."""
    return game_map.get_tile(tx, ty) in _WATER_TILES


def _find_shore_positions(game_map, cx: float, cy: float,
                          search_radius_tiles: int = 20,
                          max_candidates: int = 12):
    """
    (cx, cy) 픽셀 위치 주변에서 '물가'(물 타일이면서 옆이 육지인 경계)
    위치들을 거리순으로 정렬해 픽셀 좌표 리스트로 반환.
    """
    origin_tx = int(cx // TILE_SIZE)
    origin_ty = int(cy // TILE_SIZE)
    candidates = []
    for dy in range(-search_radius_tiles, search_radius_tiles + 1):
        for dx in range(-search_radius_tiles, search_radius_tiles + 1):
            tx, ty = origin_tx + dx, origin_ty + dy
            if not _is_water(game_map, tx, ty):
                continue
            # 상하좌우 중 하나라도 물이 아니면 물가
            if any(not _is_water(game_map, tx + ndx, ty + ndy)
                   for ndx, ndy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                px = (tx + 0.5) * TILE_SIZE
                py = (ty + 0.5) * TILE_SIZE
                dist = math.hypot(px - cx, py - cy)
                candidates.append((dist, px, py))
    candidates.sort()
    return [(px, py) for _, px, py in candidates[:max_candidates]]


# ════════════════════════════════════════════════
#  Anaconda
# ════════════════════════════════════════════════

class Anaconda(Predator):
    """
    아나콘다 클래스.

    행동 흐름:
      [물속] idle(배회) → waiting(발견·정지) → rushing(기습)
          기습 성공 → choke + eat
          기습 실패 → chasing(추격)
      [육지] 최대속도·가속도·스태미나 감소 패널티
             추격 중이 아니면 물가로 복귀하려 배회
    """

    SPECIES_VISION_RANGE: float = 200.0
    SPECIES_VISION_ANGLE: float = 130.0
    minimap_color = (255, 255, 0)

    # 행동 상태 상수
    _STATE_IDLE    = "idle"
    _STATE_WAITING = "waiting"
    _STATE_RUSHING = "rushing"
    _STATE_CHASING = "chasing"

    HUNT_TARGETS     = {"Capybara", "Monkey", "Parrot", "ToxicFrog"}
    HATCH_TIME       = 90.0    # 아나콘다 알 부화 시간 (초)
    WATER_PREY_RANGE = 160.0   # 피식자 주변 이 거리 이내에 물이 있어야 타겟으로 삼음

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

        # ── 아나콘다 전용 속성 ──
        self.choke_range: float = choke_range
        self.hidden: bool = False

        # 물속/육지 스탯
        self.water_max_speed      = water_max_speed
        self.water_max_accelerate = water_max_accelerate
        self.land_max_speed       = land_max_speed
        self.land_max_accelerate  = land_max_accelerate
        self.land_stamina_drain   = land_stamina_drain

        # 매복 상태
        self._state: str = self._STATE_IDLE
        self._ambush_timer: float = 0.0
        self._ambush_wait_time: float = ambush_wait_time
        self._ambush_rush_speed: float = 2.5
        self._target: Optional[Animal] = None

        # 배회
        self._wander_target: Optional[Tuple[float, float]] = None
        self._wander_timer: float = 0.0

        # 💡 1. 여기서 아나콘다 전용 이미지를 설정
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
        if orig_img is not None:
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
        else:
            self.image = None # 이미지가 없으면 None으로 유지 (draw 메서드에서 부모의 원형 그리기로 대체됨)

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

    # ── 물 관련 유틸 ─────────────────────────────

    def _is_water_tile(self, wx: float, wy: float, game_map) -> bool:
        """world 좌표 (wx, wy)가 물 타일인지 확인."""
        tx, ty = int(wx // TILE_SIZE), int(wy // TILE_SIZE)
        return game_map.is_water(tx, ty)

    def _prey_near_water(self, prey: Animal, game_map) -> bool:
        """피식자 주변 WATER_PREY_RANGE 이내에 물 타일이 있는지 확인."""
        px, py = prey.coordinate
        step = TILE_SIZE
        steps = int(self.WATER_PREY_RANGE / step)
        for dx in range(-steps, steps + 1):
            for dy in range(-steps, steps + 1):
                if self._is_water_tile(px + dx * step, py + dy * step, game_map):
                    return True
        return False

    def _nearest_water_point_to(self, target_coord: Tuple[float, float],
                                game_map) -> Optional[Tuple[float, float]]:
        """
        자신의 hunt_range 내 물 타일 중 target_coord에 가장 가까운
        타일의 중심 좌표 반환. 없으면 None.
        """
        ox, oy = self.coordinate
        tx, ty = target_coord
        step = TILE_SIZE
        steps = int(self.hunt_range / step)

        best_point = None
        best_dist  = float('inf')
        for dx in range(-steps, steps + 1):
            for dy in range(-steps, steps + 1):
                wx = ox + dx * step
                wy = oy + dy * step
                if not self._is_water_tile(wx, wy, game_map):
                    continue
                d = math.hypot(wx - tx, wy - ty)
                if d < best_dist:
                    best_dist  = d
                    best_point = (wx + TILE_SIZE / 2, wy + TILE_SIZE / 2)
        return best_point

    # ── 배회 ────────────────────────────────────

    def _wander(self, dt: float, game_map):
        self._wander_timer -= dt
        if (self._wander_target is None or 
            self._wander_timer <= 0 or 
            self.distance_to(self._wander_target) < TILE_SIZE):
            
            rx = self.coordinate[0] + random.uniform(-300, 300)
            ry = self.coordinate[1] + random.uniform(-300, 300)
            
            # 맵 경계선 처리
            rx = max(50.0, min(float(game_map.pixel_width - 50.0), rx))
            ry = max(50.0, min(float(game_map.pixel_height - 50.0), ry))
            
            water_target = self._nearest_water_point_to((rx, ry), game_map)
            # 물 타일이 근처에 없으면 그냥 제한된 랜덤 좌표로 이동
            self._wander_target = water_target if water_target else (rx, ry)
            self._wander_timer  = random.uniform(3.0, 6.0)
            
        if self._wander_target:
            # 스태미나 여유가 있으면 물속에서 살짝 더 빠르게 배회
            speed_mul = 0.6 if self.environment_status == 'water' and self.stamina > 40 else 0.4
            self.move(dt, self._wander_target, speed_multiplier=speed_mul)
        else:
            self.move(dt)

    # ── 기습 성공 확률 계산 ──────────────────────

    def _calc_ambush_success_rate(self, target: Animal) -> float:
        """아나콘다가 배고플수록, 피식자의 HP/스태미나가 낮을수록 성공률 상승."""
        base = 0.55
        hunger_bonus         = (self.hunger / 100.0) * 0.20
        prey_hp_bonus        = (1.0 - target.hp / target.max_hp) * 0.10
        prey_stamina_bonus   = (1.0 - target.stamina / target.max_stamina) * 0.10
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

    # ── 행동 FSM ────────────────────────────────

    def _update_behavior(self, dt: float, animals: List[Animal], game_map):
        state = self._state

        # ── idle: 물속 배회, 물가 피식자 탐색 ──
        if state == self._STATE_IDLE:
            self.hide()
            if self.hunger < self.hunger_limit:
                self._wander(dt, game_map)   # 배부르면 자유 배회
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
                self._wander(dt, game_map)
                return

            closest = min(prey_list, key=lambda a: self.distance_to(a))

            # 물속에서 피식자에게 최대한 접근 (물 타일 중 피식자와 가장 가까운 점)
            approach = self._nearest_water_point_to(closest.coordinate, game_map)
            if approach and self.distance_to(approach) > self.attack_range:
                self.move(dt, approach)          # 아직 물속 접근 중
            else:
                self._set_state(self._STATE_WAITING, closest)  # 충분히 접근 → 기습 대기
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
                if random.random() < self._calc_ambush_success_rate(t):
                    # 기습 성공 → choke + 처치
                    self.choke(t, dt)
                    self.attack(t, damage=30.0)
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
                    self.attack(t, damage=25.0)
                    if not t.alive:
                        self.eat(40.0)
                        self._set_state(self._STATE_IDLE)

            # 너무 멀어지거나 스태미나 소진 시 포기
            if self.distance_to(t) > self.hunt_range * 1.5 or self.stamina <= 0:
                self._set_state(self._STATE_IDLE)

    # ── 업데이트 ─────────────────────────────────

    def update(self, dt: float, game_map, weather, animals: List[Animal]):
        # 💡 Predator의 기본 자동 사냥 로직을 건너뛰기 위해
        #    super().update()(=Predator.update) 대신 Animal.update를 직접 호출한다.
        #    이렇게 하면 나이/갈증/스태미나 등 공통 처리는 그대로 돌면서
        #    포식 행동은 아래 매복 FSM이 단독으로 제어한다.
        Animal.update(self, dt, game_map, weather, animals)
        if not self.alive:
            return

        self._apply_environment_stats(game_map)
        self._apply_land_stamina_drain(dt)

        # 물속일 때만 매복 FSM 작동
        # 육지에서는 은신 해제, 추격 중이면 계속 추격, 아니면 물가로 복귀하려 배회
        if self.environment_status == "water":
            self._update_behavior(dt, animals, game_map)
        else:
            if self.hidden:
                self.stop_hide()
            if self._state == self._STATE_CHASING:
                self._update_behavior(dt, animals, game_map)
            else:
                # 육지 + 비추격: 멈춰 있지 않도록 배회(배회 목표가 물 쪽으로 잡혀 자연스럽게 물로 복귀)
                self._wander(dt, game_map)
                # 물속에서 잡았던 매복 상태(waiting/rushing)는 초기화
                if self._state != self._STATE_IDLE:
                    self._set_state(self._STATE_IDLE)

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
        
        # 1. 화면 좌표를 먼저 계산합니다.
        sx, sy = camera.world_to_screen(self.coordinate[0], self.coordinate[1])
        
        # 💡 [최적화 핵심] 동물이 화면을 완전히 벗어났다면 아예 연산(스케일, 회전)을 하지 않고 종료합니다.
        # 여유 공간(margin)을 약 100픽셀 정도 두어 자연스럽게 사라지도록 합니다.
        margin = 100
        if not (-margin < sx < camera.screen_w + margin and -margin < sy < camera.screen_h + margin):
            return

        if self.image:
            # 만약 이미지가 정상적으로 로드되었다면 이미지로 그림
            # 화면 좌표 계산
            sx, sy = camera.world_to_screen(self.coordinate[0], self.coordinate[1])
            
            # 💡 [핵심 수정] 이미지의 현재 가로, 세로 길이에 각각 카메라 줌 비율을 곱해줍니다!
            new_w = int(self.image.get_width() * camera.zoom)
            new_h = int(self.image.get_height() * camera.zoom)
                
            # 비율이 유지된 채로 줌인/줌아웃 되도록 스케일링
            scaled_image = pygame.transform.scale(self.image, (new_w, new_h))
            scaled_image = pygame.transform.flip(scaled_image, True, False) # 뱀장어는 이미지 바라보는 방향이 반대라 좌우 반전
            scaled_image = pygame.transform.rotate(scaled_image, 20) # 뱀장어는 살짝 기울어져 있음

            # 💡 2. 진행 방향(facing_angle)을 기준으로 회전 적용
            angle_deg = math.degrees(-self.facing_angle)
            rotated_image = pygame.transform.rotate(scaled_image, angle_deg)
                
            # 이미지 출력 (중심점 맞추기)
            rect = rotated_image.get_rect(center=(sx, sy))
            screen.blit(rotated_image, rect)
                
            # 체력바 렌더링
            hp_ratio = self.hp / self.max_hp
            bar_w = 30 * camera.zoom
            bar_h = 4 * camera.zoom
            # 체력바 위치도 이미지 세로 크기에 맞춰 유동적으로 조절
            pygame.draw.rect(screen, (220, 60, 60), (sx - bar_w/2, sy - (new_h/2) - 10, bar_w, bar_h))
            pygame.draw.rect(screen, (100, 220, 120), (sx - bar_w/2, sy - (new_h/2) - 10, bar_w * hp_ratio, bar_h))
        else:
            # 이미지 로드 실패 시 기본 원으로 그리기(부모 클래스)
            super().draw(screen, camera)
    def __repr__(self):
        return (f"<Anaconda '{self.name}' hp={self.hp}/{self.max_hp} "
                f"state={self._state} hidden={self.hidden} "
                f"hunger={self.hunger:.0f} "
                f"pos=({self.coordinate[0]:.0f},{self.coordinate[1]:.0f})>")


# ════════════════════════════════════════════════
#  Crocodile  ── Bae.py의 기존 Crocodile 클래스를 이걸로 교체하세요.
#  변경점: 물에서만 스폰/서식. 배회는 물 타일만, 사냥은 물가 피식자만
#         (물 지점으로 접근, 육지로는 쫓아가지 않음). 데스롤/잠복은 유지.
# ════════════════════════════════════════════════

class Crocodile(Predator):
    """
    악어. 물에서만 사는 매복 포식자.
    idle(물속 배회) → seeking_shore(물가 이동) → lurking(잠복) → rushing(기습)
      → death_roll(데스롤) → idle
      → chasing(추격, 물가 한정) → idle
    """
    SPECIES_VISION_RANGE = 230.0
    SPECIES_VISION_ANGLE = 110.0
    HUNT_TARGETS = {"Capybara", "Monkey", "Parrot", "ToxicFrog"}
    HATCH_TIME   = 120.0
    minimap_color = (0, 128, 128)

    WATER_PREY_RANGE = 160.0   # 피식자 주변 이 거리 안에 물이 있어야 사냥 대상

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
        self.water_max_speed     = water_max_speed
        self.water_max_accel     = water_max_accel
        self.rush_max_speed      = rush_max_speed
        self.rush_max_accel      = rush_max_accel
        self.land_stamina_drain  = land_stamina_drain
        self.drink_range         = drink_range
        self.lurk_timeout        = lurk_timeout
        self.death_roll_dps      = death_roll_dps
        self.death_roll_duration = death_roll_duration

        self.submerged   = False
        self._state      = self._IDLE
        self._target     = None
        self._shore_pos  = None
        self._lurk_timer = 0.0
        self._roll_timer = 0.0

        # 배회
        self._wander_target = None
        self._wander_timer  = 0.0

        # 💡 1. 여기서 악어 전용 이미지를 설정
        self.image_path = "crocodile.png"
        self.image = None
        if self.image_path not in Bae:
            try:
                loaded_img = pygame.image.load(self.image_path).convert_alpha()
                Bae[self.image_path] = loaded_img
            except Exception as e:
                print(f"⚠️ {name} 이미지 로드 실패: {e}")
                Bae[self.image_path] = None
        orig_img = Bae[self.image_path]
        if orig_img is not None:
            orig_w, orig_h = orig_img.get_size()
            target_max_size = int(self.size * 2.5)
            scale_factor = target_max_size / max(orig_w, orig_h)
            new_w = int(orig_w * scale_factor)
            new_h = int(orig_h * scale_factor)
            self.image = pygame.transform.scale(orig_img, (new_w, new_h))
        else:
            self.image = None

    # ── 물 관련 유틸 (아나콘다와 동일 개념) ──────

    def _prey_near_water(self, prey, game_map) -> bool:
        """피식자 주변 WATER_PREY_RANGE 이내에 물 타일이 있는지 확인."""
        px, py = prey.coordinate
        ptx, pty = int(px // TILE_SIZE), int(py // TILE_SIZE)
        steps = int(self.WATER_PREY_RANGE / TILE_SIZE)
        for dx in range(-steps, steps + 1):
            for dy in range(-steps, steps + 1):
                if _is_water(game_map, ptx + dx, pty + dy):
                    return True
        return False

    def _nearest_water_point_to(self, target_coord, game_map):
        """hunt_range 내 물 타일 중 target_coord에 가장 가까운 타일 중심 반환."""
        ox, oy = self.coordinate
        tx, ty = target_coord
        otx, oty = int(ox // TILE_SIZE), int(oy // TILE_SIZE)
        steps = int(self.hunt_range / TILE_SIZE)
        best, best_d = None, float('inf')
        for dx in range(-steps, steps + 1):
            for dy in range(-steps, steps + 1):
                wtx, wty = otx + dx, oty + dy
                if not _is_water(game_map, wtx, wty):
                    continue
                wx = wtx * TILE_SIZE + TILE_SIZE / 2
                wy = wty * TILE_SIZE + TILE_SIZE / 2
                d = math.hypot(wx - tx, wy - ty)
                if d < best_d:
                    best_d, best = d, (wx, wy)
        return best

    # ── 상태 전환 ───────────────────────────────

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

    # ── 헬퍼 ────────────────────────────────────

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

    # ── 배회 (물 타일만) ────────────────────────

    def _wander(self, dt, game_map):
        self._wander_timer -= dt
        if (self._wander_target is None or
            self._wander_timer <= 0 or
            self.distance_to(self._wander_target) < TILE_SIZE):

            cx = int(self.coordinate[0] // TILE_SIZE)
            cy = int(self.coordinate[1] // TILE_SIZE)
            self._wander_target = None

            # 💡 물 타일만 배회 목표로 선택
            for _ in range(25):
                tx = cx + random.randint(-10, 10)
                ty = cy + random.randint(-10, 10)
                if (0 <= tx < game_map.map_width and 0 <= ty < game_map.map_height
                        and game_map.is_water(tx, ty)):
                    self._wander_target = (tx * TILE_SIZE + TILE_SIZE / 2,
                                           ty * TILE_SIZE + TILE_SIZE / 2)
                    break

            if not self._wander_target:
                # 주변에 물이 없으면 가장 가까운 물 지점으로 복귀
                back = self._nearest_water_point_to(tuple(self.coordinate), game_map)
                self._wander_target = back if back else (self.coordinate[0], self.coordinate[1])

            self._wander_timer = random.uniform(3.0, 6.0)

        if self._wander_target:
            speed_mul = 0.6 if self.environment_status == 'water' and self.stamina > 50 else 0.4
            self.move(dt, self._wander_target, speed_multiplier=speed_mul)
        else:
            self.move(dt)

    # ── 행동 FSM ────────────────────────────────

    def _update_behavior(self, dt, animals, game_map):
        s = self._state

        if s == self._IDLE:
            self.submerged = False
            self._wander(dt, game_map)
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
            # 💡 물가 근처에 있는 피식자만 사냥 대상으로
            nearby = [a for a in animals
                      if isinstance(a, Prey) and a.alive
                      and self.distance_to(a) <= self.drink_range
                      and self._prey_near_water(a, game_map)]
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
            # 💡 피식자가 물가를 벗어났으면 포기 (육지로 안 쫓아감)
            if not self._prey_near_water(t, game_map):
                self._set_state(self._IDLE); return
            # 💡 피식자에게 직진하지 않고, 피식자와 가장 가까운 '물 지점'으로 접근
            approach = self._nearest_water_point_to(t.coordinate, game_map)
            self.move(dt, approach if approach else t.coordinate, 1.0)
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
            # 💡 물가 벗어난 먹이는 포기, 추격도 물 지점 경유
            if not self._prey_near_water(t, game_map):
                self._set_state(self._IDLE); return
            approach = self._nearest_water_point_to(t.coordinate, game_map)
            self.move(dt, approach if approach else t.coordinate, self.chase_speed_mul)
            self.use_stamina(12.0 * dt)
            if self.distance_to(t) <= self.attack_range:
                if random.random() < self.attack_success_rate:
                    self.attack(t, damage=40.0)
                    if not t.alive:
                        self.eat(50.0)
                        self._set_state(self._IDLE)
            if self.distance_to(t) > self.hunt_range or self.stamina <= 0:
                self._set_state(self._IDLE)

    # ── 업데이트 ─────────────────────────────────

    def update(self, dt, game_map, weather, animals):
        # 💡 Predator.update의 자동 사냥 로직과 충돌하지 않도록 Animal.update를 직접 호출.
        Animal.update(self, dt, game_map, weather, animals)
        if not self.alive:
            return

        # 커플 맺기 시도
        if self.couple is None:
            for a in animals:
                if self.try_form_couple(a):
                    break

        self._apply_land_drain(dt)

        # 💡 어쩌다 육지에 올라왔다면, 사냥/잠복을 멈추고 물로 복귀
        tx = int(self.coordinate[0] // TILE_SIZE)
        ty = int(self.coordinate[1] // TILE_SIZE)
        if not game_map.is_water(tx, ty):
            self.environment_status = "land"
            if self._state != self._IDLE:
                self._set_state(self._IDLE)
            self._wander(dt, game_map)   # _wander가 물 지점을 목표로 잡아 복귀
            return

        if self._state == self._LURKING and self.environment_status != "water":
            self._set_state(self._IDLE)
        self._update_behavior(dt, animals, game_map)

    # ── 번식 ────────────────────────────────────

    def make_child(self):
        return Egg(
            coordinate=self.home_coordinate or tuple(self.coordinate),
            parent=self,
            hatch_time=self.HATCH_TIME,
        )

    def _spawn_child(self) -> "Crocodile":
        return Crocodile(
            name=f"Crocodile_{random.randint(1000, 9999)}",
            coordinate=tuple(self.coordinate),
        )

    # ── 렌더링 ──────────────────────────────────

    def draw(self, screen: pygame.Surface, camera):
        if not self.alive:
            return

        sx, sy = camera.world_to_screen(self.coordinate[0], self.coordinate[1])
        margin = 100
        if not (-margin < sx < camera.screen_w + margin and -margin < sy < camera.screen_h + margin):
            return

        if self.image:
            sx, sy = camera.world_to_screen(self.coordinate[0], self.coordinate[1])
            new_w = int(self.image.get_width() * camera.zoom)
            new_h = int(self.image.get_height() * camera.zoom)
            scaled_image = pygame.transform.scale(self.image, (new_w, new_h))
            scaled_image = pygame.transform.flip(scaled_image, True, False)
            scaled_image = pygame.transform.rotate(scaled_image, 20)
            angle_deg = math.degrees(-self.facing_angle)
            rotated_image = pygame.transform.rotate(scaled_image, angle_deg)
            rect = rotated_image.get_rect(center=(sx, sy))
            screen.blit(rotated_image, rect)

            hp_ratio = self.hp / self.max_hp
            bar_w = 30 * camera.zoom
            bar_h = 4 * camera.zoom
            pygame.draw.rect(screen, (220, 60, 60), (sx - bar_w/2, sy - (new_h/2) - 10, bar_w, bar_h))
            pygame.draw.rect(screen, (100, 220, 120), (sx - bar_w/2, sy - (new_h/2) - 10, bar_w * hp_ratio, bar_h))
        else:
            super().draw(screen, camera)



# ════════════════════════════════════════════════
#  Tarantula  ── Bae.py의 기존 Tarantula 클래스를 이걸로 교체하세요.
#  (없으면 Crocodile 다음에 붙여넣기. import/Bae 캐시는 이미 상단에 있음)
# ════════════════════════════════════════════════

class Tarantula(Predator):
    """
    타란튤라(독거미). 패시브 거미줄 트랩형 포식자.

    행동 흐름:
      wander(배회) → 자리에 도착하면 거미줄 설치(make_web) → ambush(위장 잠복)
      거미줄(web_range)에 '닿는 동물'을 bite()로 무는데:
        · 피식자(Capybara/Monkey): 거미줄에 묶어(감속) 반복해서 물어 죽인 뒤 먹음
        · 비-피식자: 한 번만 물어 독을 주입하고 풀어줌(이후 감속·재공격 없음)
        · 같은 종(타란튤라)·앵무새(비행)는 거미줄에 걸리지 않음
      한동안 아무것도 안 걸리면 자리를 옮겨(다시 wander) 거미줄을 새로 친다.

    명세: 거미줄 범위 안으로 들어온 동물에게 bite()로 독 효과를 부여.
    """

    SPECIES_VISION_RANGE: float = 130.0
    SPECIES_VISION_ANGLE: float = 360.0   # 거미줄 진동으로 전방향 감지
    HUNT_TARGETS = {"Capybara", "Monkey"}
    HATCH_TIME   = 60.0
    minimap_color = (140, 70, 20)

    # 행동 상태 상수
    _STATE_WANDER = "wander"
    _STATE_AMBUSH = "ambush"

    def __init__(
        self,
        name: str,
        coordinate: Tuple[float, float],
        web_range: float = 150.0,
        web_slow_ratio: float = 0.45,   # 거미줄에 묶인 동물 최대속도를 이 비율로 캡
        bite_damage: float = 12.0,
        bite_interval: float = 1.0,     # 피식자 연속 물기 간격(초)
        poison_duration: float = 8.0,
        poison_dps: float = 5.0,
        poison_speed_mul: float = 0.5,
        ambush_relocate_time: float = 20.0,
        **kwargs,
    ):
        super().__init__(
            name=name,
            coordinate=coordinate,
            attack_range=30.0,             # 거미줄 트랩이 트리거라 직접 사용 X
            hunt_range=web_range,
            attack_success_rate=1.0,       # 거미줄 접촉 시 무는 건 확정
            hunger_limit=40.0,
            chase_speed_mul=1.2,
            max_speed=55.0,                # 육상 소형 — 느림
            max_accelerate=160.0,
            hp=60, max_hp=60,
            size=60.0,
            **kwargs,
        )

        # ── 타란튤라 전용 속성 ──
        self.hidden: bool = False
        self.web_range: float = web_range
        self.web_slow_ratio: float = web_slow_ratio
        self.web_center: Optional[Tuple[float, float]] = None
        self.web_active: bool = False

        self.bite_damage: float = bite_damage
        self.bite_interval: float = bite_interval
        self.poison_duration: float = poison_duration
        self.poison_dps: float = poison_dps
        self.poison_speed_mul: float = poison_speed_mul

        self.ambush_relocate_time: float = ambush_relocate_time

        # 상태 머신
        self._state: str = self._STATE_WANDER
        self._ambush_timer: float = 0.0

        # 거미줄 물기 관리
        self._bite_cd: dict = {}          # id(피식자) -> 남은 물기 쿨다운(초)
        self._bitten_nonprey: set = set() # 이미 문 비-피식자 id (한 번만 물고 풀어줌)

        # 배회
        self._wander_target: Optional[Tuple[float, float]] = None
        self._wander_timer: float = 0.0

        # ── 이미지 로드 (Anaconda/Crocodile과 동일 캐시 패턴) ──
        self.image_path = "tarantula.png"
        self.image = None
        if self.image_path not in Bae:
            try:
                Bae[self.image_path] = pygame.image.load(self.image_path).convert_alpha()
            except Exception as e:
                print(f"⚠️ {name} 이미지 로드 실패: {e}")
                Bae[self.image_path] = None
        orig_img = Bae[self.image_path]
        if orig_img is not None:
            orig_w, orig_h = orig_img.get_size()
            target_max_size = int(self.size * 2.5)
            scale_factor = target_max_size / max(orig_w, orig_h)
            new_w = int(orig_w * scale_factor)
            new_h = int(orig_h * scale_factor)
            self.image = pygame.transform.scale(orig_img, (new_w, new_h))
        else:
            self.image = None

    # ── 은신 ────────────────────────────────────

    def hide(self):
        self.hidden = True

    def stop_hide(self):
        self.hidden = False

    # ── 거미줄 ──────────────────────────────────

    def make_web(self):
        """현재 위치에 거미줄을 설치한다."""
        self.web_center = (self.coordinate[0], self.coordinate[1])
        self.web_active = True
        self._bite_cd.clear()
        self._bitten_nonprey.clear()

    def clear_web(self):
        self.web_center = None
        self.web_active = False
        self._bite_cd.clear()
        self._bitten_nonprey.clear()

    def _slow(self, a: Animal):
        """거미줄에 묶인 동물의 '최대 속도'를 web_slow_ratio 비율로 캡(프레임레이트 무관)."""
        spd = math.hypot(a.velocity[0], a.velocity[1])
        limit = a.max_speed * self.web_slow_ratio
        if spd > limit and spd > 0:
            scale = limit / spd
            a.velocity[0] *= scale
            a.velocity[1] *= scale

    # ── 물기 ────────────────────────────────────

    def bite(self, target: Animal) -> bool:
        """대상을 물어 피해 + 독 주입. (거리 판정은 거미줄 접촉으로 대체)"""
        if not target.alive:
            return False
        target.take_damage(self.bite_damage, source=f"{self.name}_bite")
        target.apply_poison(
            duration=self.poison_duration,
            dps=self.poison_dps,
            speed_multiplier=self.poison_speed_mul,
        )
        target.apply_stun(0.3)
        return True

    def _feed(self, food_value: float = 35.0):
        """포식 처리. 거미는 먹이에서 수분도 얻으므로 갈증도 조금 해소."""
        self.eat(food_value)
        self.thirst = max(0.0, self.thirst - 25.0)   # 먹이에서 수분 보충(drink 메서드 비의존)

    # ── 거미줄 처리: 범위에 닿는 모든 동물 ──────

    def _process_web(self, animals: List[Animal], dt: float) -> bool:
        """
        거미줄 범위 내 모든 동물 처리.
          - 피식자: 감속 + 쿨다운마다 물기 → 죽으면 먹기
          - 비-피식자: 한 번만 물어 독 주입 후 풀어줌(이후 감속·재공격 없음)
        뭔가 걸렸으면 True 반환.
        """
        if not self.web_active or self.web_center is None:
            return False

        cx, cy = self.web_center

        # 피식자 물기 쿨다운 감소
        for k in list(self._bite_cd):
            self._bite_cd[k] -= dt
            if self._bite_cd[k] <= 0:
                del self._bite_cd[k]

        caught = False
        in_web_ids = set()

        for a in animals:
            if a is self or not a.alive:
                continue
            # 같은 종(타란튤라)과 앵무새(비행)는 거미줄에 걸리지 않음
            if type(a) is type(self) or type(a).__name__ == "Parrot":
                continue
            if math.hypot(a.coordinate[0] - cx, a.coordinate[1] - cy) > self.web_range:
                continue
            in_web_ids.add(id(a))

            if self._is_prey(a):
                # 피식자: 거미줄에 묶고(감속) 쿨다운마다 물기 → 죽으면 먹기
                self._slow(a)
                caught = True
                if id(a) not in self._bite_cd:
                    self.bite(a)
                    self._bite_cd[id(a)] = self.bite_interval
                    if not a.alive:
                        self._feed()
                        in_web_ids.discard(id(a))
            else:
                # 비-피식자: 한 번만 물어 독 주입 후 풀어줌
                if id(a) not in self._bitten_nonprey:
                    self._slow(a)
                    self.bite(a)
                    self._bitten_nonprey.add(id(a))
                    caught = True
                # 이미 문 비-피식자는 손대지 않음(풀어줌)

        # 거미줄을 벗어난 비-피식자는 기록 제거(재진입 시 다시 물 수 있게)
        self._bitten_nonprey &= in_web_ids
        return caught

    # ── 배회 ────────────────────────────────────

    def _wander(self, dt: float, game_map):
        """육지 타일 위에서만 배회한다(물 타일은 목표로 잡지 않음)."""
        self._wander_timer -= dt
        if (self._wander_target is None
                or self._wander_timer <= 0
                or self.distance_to(self._wander_target) < TILE_SIZE):
            cx = int(self.coordinate[0] // TILE_SIZE)
            cy = int(self.coordinate[1] // TILE_SIZE)
            target = None
            for _ in range(25):
                tx = cx + random.randint(-8, 8)
                ty = cy + random.randint(-8, 8)
                if (0 <= tx < game_map.map_width and 0 <= ty < game_map.map_height
                        and not game_map.is_water(tx, ty)):     # 육지 타일만
                    target = (tx * TILE_SIZE + TILE_SIZE / 2,
                              ty * TILE_SIZE + TILE_SIZE / 2)
                    break
            if target is None:
                target = (self.coordinate[0], self.coordinate[1])  # 주변에 육지 없으면 제자리
            self._wander_target = target
            self._wander_timer = random.uniform(3.0, 6.0)
        self.move(dt, self._wander_target, speed_multiplier=0.4)

    # ── 상태 전환 ───────────────────────────────

    def _set_state(self, state: str):
        self._state = state
        self._ambush_timer = 0.0

    # ── 행동 FSM ────────────────────────────────

    def _update_behavior(self, dt: float, animals: List[Animal], game_map):
        # ── 갈증 우선: 거미줄을 버리고 가장 가까운 물로 마시러 간다 ──
        if self.is_seeking_water and self._water_target is not None:
            self.stop_hide()
            if self.web_active:
                self.clear_web()
            self._state = self._STATE_WANDER   # 다 마시면 다시 배회→거미줄
            self.move(dt, self._water_target, speed_multiplier=0.7)
            return

        state = self._state

        # ── wander: 자리를 잡으면 거미줄 설치 ──
        if state == self._STATE_WANDER:
            self.stop_hide()
            if (self._wander_target is not None
                    and self.distance_to(self._wander_target) < TILE_SIZE * 1.5):
                self.stop()
                self.make_web()
                self._set_state(self._STATE_AMBUSH)
            else:
                self._wander(dt, game_map)

        # ── ambush: 위장 잠복, 거미줄 트랩 가동 ──
        elif state == self._STATE_AMBUSH:
            self.hide()
            self.stop()
            caught = self._process_web(animals, dt)
            if caught:
                self._ambush_timer = 0.0
            else:
                self._ambush_timer += dt
                # 한동안 아무것도 안 걸리면 자리를 옮겨 새 거미줄
                if self._ambush_timer >= self.ambush_relocate_time:
                    self.clear_web()
                    self._set_state(self._STATE_WANDER)

    # ── 업데이트 ─────────────────────────────────

    def update(self, dt: float, game_map, weather, animals: List[Animal]):
        # 💡 Anaconda/Crocodile과 동일: Predator.update의 자동 사냥 로직과
        #    충돌하지 않도록 Animal.update를 직접 호출하고, 사냥은 아래 FSM이 단독 제어.
        Animal.update(self, dt, game_map, weather, animals)
        if not self.alive:
            self.clear_web()
            return
        self._update_behavior(dt, animals, game_map)

    # ── 번식 ────────────────────────────────────

    def make_child(self) -> "Egg":
        return Egg(
            coordinate=self.home_coordinate or tuple(self.coordinate),
            parent=self,
            hatch_time=self.HATCH_TIME,
        )

    def _spawn_child(self) -> "Tarantula":
        return Tarantula(
            name=f"Tarantula_{random.randint(1000, 9999)}",
            coordinate=tuple(self.coordinate),
        )

    # ── 렌더링 ──────────────────────────────────

    def draw(self, screen: pygame.Surface, camera):
        if not self.alive:
            return

        sx, sy = camera.world_to_screen(self.coordinate[0], self.coordinate[1])
        margin = 100
        if not (-margin < sx < camera.screen_w + margin
                and -margin < sy < camera.screen_h + margin):
            return

        # 거미줄 시각화 (활성 상태일 때 옅은 원)
        if self.web_active and self.web_center is not None:
            wcx, wcy = camera.world_to_screen(self.web_center[0], self.web_center[1])
            web_r = max(1, int(self.web_range * camera.zoom))
            web_surf = pygame.Surface((web_r * 2 + 2, web_r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(web_surf, (230, 230, 230, 40), (web_r + 1, web_r + 1), web_r)
            pygame.draw.circle(web_surf, (230, 230, 230, 90), (web_r + 1, web_r + 1), web_r, 1)
            screen.blit(web_surf, (int(wcx) - web_r - 1, int(wcy) - web_r - 1))

        if self.image:
            new_w = int(self.image.get_width() * camera.zoom)
            new_h = int(self.image.get_height() * camera.zoom)
            scaled_image = pygame.transform.scale(self.image, (new_w, new_h))
            angle_deg = math.degrees(-self.facing_angle)
            rotated_image = pygame.transform.rotate(scaled_image, angle_deg)

            # 위장 중이면 반투명하게
            if self.hidden:
                rotated_image = rotated_image.copy()
                rotated_image.set_alpha(110)

            rect = rotated_image.get_rect(center=(sx, sy))
            screen.blit(rotated_image, rect)

            hp_ratio = self.hp / self.max_hp
            bar_w = 30 * camera.zoom
            bar_h = 4 * camera.zoom
            pygame.draw.rect(screen, (220, 60, 60),
                             (sx - bar_w / 2, sy - (new_h / 2) - 10, bar_w, bar_h))
            pygame.draw.rect(screen, (100, 220, 120),
                             (sx - bar_w / 2, sy - (new_h / 2) - 10, bar_w * hp_ratio, bar_h))
        else:
            super().draw(screen, camera)

    def __repr__(self):
        return (f"<Tarantula '{self.name}' hp={self.hp}/{self.max_hp} "
                f"state={self._state} hidden={self.hidden} web={self.web_active} "
                f"hunger={self.hunger:.0f} "
                f"pos=({self.coordinate[0]:.0f},{self.coordinate[1]:.0f})>")
