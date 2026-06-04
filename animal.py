import math
import random
import pygame
from typing import Tuple, Optional, List

TILE_SIZE = 32


# ════════════════════════════════════════════════
#  FOV 유틸리티
# ════════════════════════════════════════════════

def _angle_diff(a: float, b: float) -> float:
    d = (b - a) % (2 * math.pi)
    if d > math.pi:
        d -= 2 * math.pi
    return d


def _line_blocked_by_trees(ox: float, oy: float,
                            tx: float, ty: float,
                            game_map) -> bool:
    dist = math.hypot(tx - ox, ty - oy)
    if dist < 1.0:
        return False
    steps = max(4, int(dist / 24))
    dx = (tx - ox) / steps
    dy = (ty - oy) / steps
    for i in range(1, steps):
        sx = ox + dx * i
        sy = oy + dy * i
        tree = game_map.tree_map.get((int(sx // TILE_SIZE), int(sy // TILE_SIZE)))
        if tree and not tree.broken and tree.canopy_rect().collidepoint(sx, sy):
            return True
    return False


def has_line_of_sight(observer, target_coord: Tuple[float, float],
                      game_map) -> bool:
    ox, oy = observer.coordinate[0], observer.coordinate[1]
    tx, ty = target_coord[0], target_coord[1]

    if math.hypot(tx - ox, ty - oy) > observer.vision_range:
        return False

    if observer.vision_angle < 360:
        diff = abs(_angle_diff(observer.facing_angle,
                               math.atan2(ty - oy, tx - ox)))
        if diff > math.radians(observer.vision_angle / 2):
            return False

    return not _line_blocked_by_trees(ox, oy, tx, ty, game_map)


# ════════════════════════════════════════════════
#  Egg
# ════════════════════════════════════════════════

class Egg:
    """
    알 클래스. 부모 동물이 번식 시 생성되며, hatch_time 초 후 부화한다.

    사용 흐름:
        1. Animal._update_home() → Egg 생성 후 반환
        2. system.py에서 eggs 리스트를 관리하며 매 프레임 egg.update(dt) 호출
        3. update()가 Animal 인스턴스를 반환하면 animals 리스트에 추가
    """

    def __init__(
        self,
        coordinate: Tuple[float, float],
        parent: "Animal",
        hatch_time: float = 60.0,
    ):
        self.coordinate = list(coordinate)
        self.parent = parent          # 부모 참조 (make_child 호출용)
        self.hatch_time = hatch_time
        self.hatch_timer = 0.0
        self.hatched = False

    def update(self, dt: float) -> Optional["Animal"]:
        """
        매 프레임 호출. 부화 시 make_child()로 자식 생성 후 반환.
        부화 전이면 None 반환.
        """
        if self.hatched:
            return None
        self.hatch_timer += dt
        if self.hatch_timer >= self.hatch_time:
            self.hatched = True
            # _spawn_child()가 있으면 그걸 호출, 없으면 make_child() 폴백
            spawn_fn = getattr(self.parent, '_spawn_child', self.parent.make_child)
            child = spawn_fn()
            if child:
                child.coordinate = self.coordinate[:]
                print(f"{self.parent.name}의 알이 부화했다!")
            return child
        return None

    @property
    def hatch_progress(self) -> float:
        """부화 진행률 0.0 ~ 1.0"""
        return min(1.0, self.hatch_timer / self.hatch_time)

    def draw(self, screen: "pygame.Surface", camera):
        """알 렌더링: 작은 타원 + 부화 진행 바."""
        if self.hatched:
            return
        sx, sy = camera.world_to_screen(self.coordinate[0], self.coordinate[1])
        pygame.draw.ellipse(screen, (210, 200, 170),
                            (int(sx) - 5, int(sy) - 4, 10, 8))
        bw = 12
        bx, by = int(sx) - bw // 2, int(sy) - 10
        pygame.draw.rect(screen, (60, 60, 60), (bx, by, bw, 2))
        pygame.draw.rect(screen, (255, 200, 50),
                         (bx, by, int(bw * self.hatch_progress), 2))

    def __repr__(self):
        return (f"<Egg parent={self.parent.name} "
                f"progress={self.hatch_progress:.0%}>")


# ════════════════════════════════════════════════
#  Animal
# ════════════════════════════════════════════════

class Animal:
    """
    공통 속성·메서드 정의. 모든 동물 클래스는 이 클래스(또는 하위 클래스)를 상속한다.

    하위 클래스에서 반드시 설정할 클래스 변수:
        SPECIES_VISION_RANGE : float  — 시야 거리 (픽셀)
        SPECIES_VISION_ANGLE : float  — 시야각 (도, 360 = 전방향)
    """

    SPECIES_VISION_RANGE: float = 150.0
    SPECIES_VISION_ANGLE: float = 120.0
    HATCH_TIME: float = 60.0  # 알 부화 시간 (초). 하위 클래스에서 덮어쓰기 가능.

    def __init__(
        self,
        name: str,
        coordinate: Tuple[float, float],
        hp: int = 100,
        max_hp: int = 100,
        stamina: float = 100.0,
        max_stamina: float = 100.0,
        max_speed: float = 80.0,
        hunger: float = 0.0,
        thirst: float = 0.0,
        detection_range: float = 150.0,
        age: int = 0,
        max_age: int = 3600,
        sex: str = "male",
        home_coordinate: Optional[Tuple[float, float]] = None,
        environment_status: str = "land",
        max_accelerate: float = 200.0,
    ):
        # 기본 정보
        self.name = name
        self.coordinate = list(coordinate)
        self.velocity = [0.0, 0.0]

        # 체력 / 스태미나
        self.hp = hp
        self.max_hp = max_hp
        self.stamina = stamina
        self.max_stamina = max_stamina

        # 이동
        self.max_accelerate = max_accelerate
        self.max_speed = max_speed

        # 욕구
        self.hunger = hunger
        self.thirst = thirst

        # 환경 / 나이
        self.environment_status = environment_status
        self.age = age
        self.max_age = max_age
        self.is_adult = False

        # 성별 / 번식
        self.sex = sex
        self.couple: Optional["Animal"] = None
        self.can_breed = False

        # 둥지
        self.home_coordinate = list(home_coordinate) if home_coordinate else None
        self.at_home = False
        self.home_threshold = 40.0
        self.home_build_prob = 0.002
        self.breed_prob = 0.001
        self.home_range = 80.0
        self._home_timer = 0.0

        # 상태 이상
        self.is_stunned = False
        self.stun_timer = 0.0
        self.is_poisoned = False
        self.poison_timer = 0.0
        self.poison_damage_per_sec = 2.0
        self.poison_speed_multiplier = 0.6

        # 인식
        self.detection_range = detection_range

        # 시야 (FOV)
        self.vision_range: float = self.SPECIES_VISION_RANGE
        self.vision_angle: float = self.SPECIES_VISION_ANGLE
        self.facing_angle: float = 0.0

        # 내부 타이머
        self.age_timer = 0.0
        self.hunger_timer = 0.0

        # 물 찾기
        self.is_seeking_water = False
        self._water_target: Optional[Tuple[float, float]] = None
        self.THIRST_SEEK_THRESHOLD = 65.0  # 물 찾기 시작 임계값

        # 생존
        self.alive = True

    # ── 가속도 (hunger / stamina에 따라 감소) ────

    @property
    def accelerate(self) -> float:
        """
        실제 가속도 = max_accelerate * hunger_factor * stamina_factor
        배고픔이 최대일 때 0.5배, 스태미나가 0일 때 추가 0.5배.
        """
        hunger_factor  = 1.0 - (self.hunger / 100.0) * 0.5
        stamina_factor = 0.5 if self.stamina <= 0 else 1.0
        return self.max_accelerate * hunger_factor * stamina_factor

    # ── 시야 (FOV) ─────────────────────────────

    def can_see(self, target: "Animal", game_map) -> bool:
        if not target.alive:
            return False
        # 물속 대상은 시야 거리 0.5배 적용
        if target.environment_status == "water":
            self.vision_range *= 0.5
            result = has_line_of_sight(self, target.coordinate, game_map)
            self.vision_range *= 2.0
            return result
        return has_line_of_sight(self, target.coordinate, game_map)

    def can_see_point(self, point: Tuple[float, float], game_map) -> bool:
        return has_line_of_sight(self, point, game_map)

    def get_visible_animals(self, animals: List["Animal"], game_map) -> List["Animal"]:
        return [a for a in animals if a is not self and self.can_see(a, game_map)]

    def _update_facing(self):
        if math.hypot(*self.velocity) > 5.0:
            self.facing_angle = math.atan2(self.velocity[1], self.velocity[0])

    def draw_fov_debug(self, screen: pygame.Surface, camera,
                       color=(80, 80, 0), alpha: int = 40):
        """시야 부채꼴 디버그 렌더링. system.py에서 원하는 키에 연결해서 사용."""
        sx, sy = camera.world_to_screen(self.coordinate[0], self.coordinate[1])
        r = int(self.vision_range * camera.zoom)
        surf = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        c = (r + 1, r + 1)
        if self.vision_angle >= 360:
            pygame.draw.circle(surf, (*color, alpha), c, r)
        else:
            half = math.radians(self.vision_angle / 2)
            start = math.degrees(self.facing_angle - half)
            end   = math.degrees(self.facing_angle + half)
            pts = [c]
            for i in range(21):
                a = math.radians(start + (end - start) * i / 20)
                pts.append((c[0] + math.cos(a) * r, c[1] + math.sin(a) * r))
            pygame.draw.polygon(surf, (*color, alpha), pts)
        screen.blit(surf, (int(sx) - r - 1, int(sy) - r - 1))

    # ── 이동 ────────────────────────────────────

    def move(self, dt: float, target: Optional[Tuple[float, float]] = None,
             speed_multiplier: float = 1.0):
        if not self.alive or self.is_stunned:
            self._apply_friction(dt)
            return

        if target is not None:
            dx = target[0] - self.coordinate[0]
            dy = target[1] - self.coordinate[1]
            dist = math.hypot(dx, dy)
            if dist > 1.0:
                self.velocity[0] += dx / dist * self.accelerate * dt
                self.velocity[1] += dy / dist * self.accelerate * dt

        spd = math.hypot(*self.velocity)
        poison_mul  = self.poison_speed_multiplier if self.is_poisoned else 1.0
        stamina_mul = 0.5 if self.stamina <= 0 else 1.0
        limit = self.max_speed * speed_multiplier * self._home_speed_multiplier() * poison_mul * stamina_mul
        if spd > limit:
            self.velocity[0] = self.velocity[0] / spd * limit
            self.velocity[1] = self.velocity[1] / spd * limit

        self.coordinate[0] += self.velocity[0] * dt
        self.coordinate[1] += self.velocity[1] * dt
        self._apply_friction(dt)
        self._update_facing()

    def _apply_friction(self, dt: float):
        spd = math.hypot(*self.velocity)
        if spd < 1.0:
            self.velocity = [0.0, 0.0]
            return
        new_spd = max(0.0, spd - self.accelerate * dt)
        self.velocity[0] = self.velocity[0] / spd * new_spd
        self.velocity[1] = self.velocity[1] / spd * new_spd

    def stop(self):
        self.velocity = [0.0, 0.0]

    # ── 체력 / 스태미나 ─────────────────────────

    def take_damage(self, amount: float, source: str = "unknown"):
        if not self.alive:
            return
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self._die(cause=source)

    def heal(self, amount: float):
        if not self.alive:
            return
        self.hp = min(self.max_hp, self.hp + amount)

    def use_stamina(self, amount: float) -> bool:
        if self.stamina < amount:
            return False
        self.stamina -= amount
        return True

    def recover_stamina(self, dt: float, rate: float = 10.0,
                        hunger_cost: float = 0.1):
        penalty = max(0.0, (self.hunger - 50) / 100)
        recovered = rate * (1.0 - penalty * 0.5) * dt
        self.stamina = min(self.max_stamina, self.stamina + recovered)
        self.hunger  = min(100.0, self.hunger + hunger_cost * dt)

    # ── 먹기 / 마시기 ───────────────────────────

    def eat(self, food_value: float = 30.0):
        self.hunger = max(0.0, self.hunger - food_value)
        self.heal(food_value * 0.1)

    def drink(self, water_value: float = 30.0):
        self.thirst = max(0.0, self.thirst - water_value)

    # ── 공격 ────────────────────────────────────

    def attack(self, target: "Animal", damage: float = 10.0):
        if not self.alive or not target.alive:
            return
        target.take_damage(damage, source=self.name)

    # ── 거리 / 위치 ─────────────────────────────

    def distance_to(self, other) -> float:
        if isinstance(other, Animal):
            tx, ty = other.coordinate[0], other.coordinate[1]
        else:
            tx, ty = other[0], other[1]
        return math.hypot(self.coordinate[0] - tx, self.coordinate[1] - ty)

    def is_at_home(self) -> bool:
        if self.home_coordinate is None:
            return False
        return self.distance_to(self.home_coordinate) <= self.home_threshold

    def near_home(self) -> bool:
        if self.home_coordinate is None:
            return False
        return self.distance_to(self.home_coordinate) <= self.home_range

    def _home_speed_multiplier(self) -> float:
        return 1.15 if self.near_home() else 1.0

    def detect_nearby(self, animals: List["Animal"], game_map=None) -> List["Animal"]:
        if game_map is not None:
            return self.get_visible_animals(animals, game_map)
        return [a for a in animals
                if a is not self and a.alive
                and self.distance_to(a) <= self.vision_range]

    # ── 커플 맺기 ────────────────────────────────

    COUPLE_RANGE: float = 80.0  # 하위 클래스에서 덮어쓰기 가능

    def try_form_couple(self, other: "Animal") -> bool:
        """
        other와 커플 맺기 시도.
        조건: 둘 다 성체, 커플 없음, 같은 종, COUPLE_RANGE 이내.
        """
        if (self.is_adult and other.is_adult
                and self.couple is None and other.couple is None
                and type(self) is type(other)
                and self.distance_to(other) <= self.COUPLE_RANGE):
            self.couple = other
            other.couple = self
            return True
        return False

    # ── 집 / 번식 ───────────────────────────────

    def _update_home(self, dt: float):
        self._home_timer += dt
        if self._home_timer < 1.0:
            return
        self._home_timer = 0.0

        c = self.couple
        # 집 짓기 — 커플이 있고, 집이 없고, 둘이 home_threshold 이내에 있을 때
        if (c is not None and c.alive
                and self.home_coordinate is None
                and self.distance_to(c) <= self.home_threshold):
            if random.random() < self.home_build_prob:
                mid = [(self.coordinate[0] + c.coordinate[0]) / 2,
                       (self.coordinate[1] + c.coordinate[1]) / 2]
                self.home_coordinate = mid
                c.home_coordinate = mid[:]
                print(f"{self.name} 집 생성: {mid}")

        # 번식 — 집에 있고, 번식 가능하고, 커플도 집에 있을 때
        if (self.home_coordinate is not None
                and self.at_home and self.can_breed
                and c is not None and c.alive and c.at_home):
            if random.random() < self.breed_prob:
                result = self.make_child()
                if result:
                    print(f"{self.name} 번식 성공!")
                return result

        return None

    def _update_home_buff(self, dt: float):
        if self.near_home():
            self.heal(3.0 * dt)
            self.stamina = min(self.max_stamina, self.stamina + 5.0 * dt)

    def make_child(self):
        """
        번식 결과 반환. 하위 클래스에서 오버라이딩.
        - 난생(알): Egg(coordinate=..., parent=self, hatch_time=self.HATCH_TIME) 반환
        - 태생(새끼): Animal 인스턴스 직접 반환
        기본값은 None (번식 없음).
        """
        return None

    def _check_can_breed(self):
        self.can_breed = (
            self.is_adult
            and self.hunger < 60
            and self.hp > self.max_hp * 0.4
        )

    # ── 상태 이상 ────────────────────────────────

    def apply_stun(self, duration: float = 2.0):
        self.is_stunned = True
        self.stun_timer = max(self.stun_timer, duration)

    def apply_poison(self, duration: float = 5.0, dps: float = 2.0,
                     speed_multiplier: float = 0.6):
        self.is_poisoned = True
        self.poison_timer = max(self.poison_timer, duration)
        self.poison_damage_per_sec = max(self.poison_damage_per_sec, dps)
        self.poison_speed_multiplier = min(self.poison_speed_multiplier, speed_multiplier)

    # ── 내부 업데이트 ────────────────────────────

    def _update_age(self, dt: float):
        self.age_timer += dt
        if self.age_timer >= 1.0:
            self.age += int(self.age_timer)
            self.age_timer %= 1.0
        self.is_adult = self.age >= self.max_age * 0.15
        if self.age >= self.max_age:
            self._die(cause="old_age")

    def _update_hunger_thirst(self, dt: float):
        self.hunger_timer += dt

        if self.hunger_timer >= 1.0:
            self.hunger = min(100.0, self.hunger + 0.8)
            self.hunger_timer = 0.0
            if self.hunger >= 100.0:
                self._die(cause="starvation")

        # 갈증 — 환경·활동 상태에 따라 다른 증감률
        if self.environment_status == "water":
            # 물속: 갈증 감소
            self.thirst = max(0.0, self.thirst - 8.0 * dt)
            if self.thirst <= 0:
                self.is_seeking_water = False
                self._water_target = None
        else:
            # 물 밖: 활동량에 따라 증가
            is_active = math.hypot(*self.velocity) > self.max_speed * 0.6
            rate = 0.55 if is_active else 0.18
            self.thirst = min(100.0, self.thirst + rate * dt)
            if self.thirst >= 100.0:
                self._die(cause="dehydration")

    def _find_nearest_water(self, game_map) -> Optional[Tuple[float, float]]:
        """현재 위치에서 가장 가까운 물 타일 중심 좌표 반환. 없으면 None."""
        from map_system import TileType
        cx = int(self.coordinate[0] // TILE_SIZE)
        cy = int(self.coordinate[1] // TILE_SIZE)
        best, best_dist = None, float('inf')
        for dy in range(-40, 41):
            for dx in range(-40, 41):
                tx, ty = cx + dx, cy + dy
                tile = game_map.get_tile(tx, ty)
                if tile in (TileType.WATER, TileType.DEEP_WATER):
                    d = math.hypot(dx, dy)
                    if d < best_dist:
                        best_dist = d
                        best = (tx * TILE_SIZE + TILE_SIZE // 2,
                                ty * TILE_SIZE + TILE_SIZE // 2)
        return best

    def _update_thirst_behavior(self, dt: float, game_map):
        """
        현재 타일에 따라 environment_status 갱신.
        갈증 임계값 초과 시 물 타일로 이동 목표 설정.
        """
        from map_system import TileType
        tx = int(self.coordinate[0] // TILE_SIZE)
        ty = int(self.coordinate[1] // TILE_SIZE)
        tile = game_map.get_tile(tx, ty)
        in_water = tile in (TileType.WATER, TileType.DEEP_WATER)
        self.environment_status = "water" if in_water else "land"

        # 목표 도달 시 초기화
        if in_water and self.thirst <= 0:
            self.is_seeking_water = False
            self._water_target = None

        # 갈증 임계값 초과 시 물 목표 설정
        if (not in_water
                and self.thirst >= self.THIRST_SEEK_THRESHOLD
                and not self.is_seeking_water):
            self.is_seeking_water = True
            self._water_target = self._find_nearest_water(game_map)

    def _update_status_effects(self, dt: float):
        if self.is_stunned:
            self.stun_timer -= dt
            if self.stun_timer <= 0:
                self.is_stunned = False
        if self.is_poisoned:
            self.poison_timer -= dt
            self.take_damage(self.poison_damage_per_sec * dt, source="poison")
            if self.poison_timer <= 0:
                self.is_poisoned = False
                self.poison_speed_multiplier = 0.6

    def _die(self, cause: str = "unknown"):
        self.alive = False
        self.velocity = [0.0, 0.0]
        print(f"{self.name} 사망 (원인: {cause})")

    # ── 메인 업데이트 ────────────────────────────

    def update(self, dt: float, game_map, weather, animals: List["Animal"]):
        if not self.alive:
            return
        self._update_age(dt)
        self._update_thirst_behavior(dt, game_map)
        self._update_hunger_thirst(dt)
        self._update_status_effects(dt)
        self.recover_stamina(dt)
        self._check_can_breed()
        self.at_home = self.is_at_home()
        self._update_home(dt)
        self._update_home_buff(dt)

    # ── 렌더링 ──────────────────────────────────

    def draw(self, screen: pygame.Surface, camera):
        if not self.alive:
            return
        sx, sy = camera.world_to_screen(self.coordinate[0], self.coordinate[1])
        pygame.draw.circle(screen, (220, 220, 220), (int(sx), int(sy)), 8)
        bw = 20
        bx, by = int(sx) - bw // 2, int(sy) - 14
        pygame.draw.rect(screen, (80, 0, 0),   (bx, by, bw, 3))
        pygame.draw.rect(screen, (0, 200, 60), (bx, by, int(bw * self.hp / self.max_hp), 3))
        if self.is_stunned:
            pygame.draw.circle(screen, (255, 255, 0),   (int(sx) + 8, int(sy) - 10), 3)
        if self.is_poisoned:
            pygame.draw.circle(screen, (100, 255, 100), (int(sx) - 8, int(sy) - 10), 3)

    def __repr__(self):
        return (f"<{self.__class__.__name__} '{self.name}' "
                f"hp={self.hp}/{self.max_hp} "
                f"pos=({self.coordinate[0]:.0f},{self.coordinate[1]:.0f})>")


# ════════════════════════════════════════════════
#  Predator
# ════════════════════════════════════════════════

class Predator(Animal):
    """
    포식자 공통 클래스.
    하위 클래스에서 설정: SPECIES_VISION_RANGE, SPECIES_VISION_ANGLE, HUNT_TARGETS
    """

    HUNT_TARGETS: set = set()  # 사냥 대상 클래스 이름. 하위 클래스에서 오버라이딩.

    def _is_prey(self, animal: "Animal") -> bool:
        return type(animal).__name__ in self.HUNT_TARGETS

    def __init__(
        self,
        name: str,
        coordinate: Tuple[float, float],
        attack_range: float = 40.0,
        hunt_range: float = 200.0,
        attack_success_rate: float = 0.6,
        hunger_limit: float = 50.0,
        chase_speed_mul: float = 1.4,
        **kwargs,
    ):
        super().__init__(name, coordinate, **kwargs)
        self.attack_range = attack_range
        self.hunt_range = hunt_range
        self.attack_success_rate = attack_success_rate
        self.hunger_limit = hunger_limit
        self.chase_speed_mul = chase_speed_mul
        self.is_hunting = False
        self.hunting_target: Optional[Animal] = None

    def find_target(self, animals: List[Animal], game_map) -> Optional[Animal]:
        """시야 안에서 가장 가까운 먹잇감 반환."""
        candidates = [
            a for a in animals
            if self._is_prey(a) and a.alive
            and self.distance_to(a) <= self.hunt_range
            and self.can_see(a, game_map)
        ]
        return min(candidates, key=lambda a: self.distance_to(a), default=None)

    def start_hunt(self, target: Animal):
        self.is_hunting = True
        self.hunting_target = target

    def stop_hunt(self):
        self.is_hunting = False
        self.hunting_target = None

    def try_attack(self, target: Animal, base_damage: float = 20.0,
                   food_value: float = 30.0) -> bool:
        if not target.alive:
            self.stop_hunt()
            return False
        if self.distance_to(target) <= self.attack_range:
            if random.random() < self.attack_success_rate:
                self.attack(target, base_damage)
                if not target.alive:
                    self.eat(food_value)
                return True
        return False

    def update(self, dt: float, game_map, weather, animals: List[Animal]):
        super().update(dt, game_map, weather, animals)
        if not self.alive or self.is_stunned:
            return

        if not self.is_hunting and self.hunger >= self.hunger_limit:
            target = self.find_target(animals, game_map)
            if target:
                self.start_hunt(target)

        if self.is_hunting and self.hunting_target:
            t = self.hunting_target
            if not t.alive or not self.can_see(t, game_map):
                self.stop_hunt()
            else:
                self.try_attack(t)
                self.move(dt, t.coordinate, self.chase_speed_mul)
                self.use_stamina(8.0 * dt)
        elif self.is_seeking_water and self._water_target:
            self.move(dt, self._water_target)
        else:
            self.move(dt)


# ════════════════════════════════════════════════
#  Prey
# ════════════════════════════════════════════════

class Prey(Animal):
    """
    피식자 공통 클래스.
    하위 클래스에서 설정: SPECIES_VISION_RANGE, SPECIES_VISION_ANGLE
    """

    def __init__(
        self,
        name: str,
        coordinate: Tuple[float, float],
        danger_range: float = 180.0,
        hide_success_rate: float = 0.5,
        hide_range: float = 80.0,
        flee_speed_mul: float = 1.5,
        **kwargs,
    ):
        super().__init__(name, coordinate, **kwargs)
        self.predator_detected = False
        self.danger_range = danger_range
        self.is_fleeing = False
        self.is_hiding = False
        self.hide_success_rate = hide_success_rate
        self.hide_range = hide_range
        self.flee_speed_mul = flee_speed_mul
        self._hiding_from: Optional[Animal] = None

    def detect_predators(self, animals: List[Animal], game_map) -> List[Animal]:
        return [
            a for a in animals
            if isinstance(a, Predator) and a.alive
            and self.distance_to(a) <= self.danger_range
            and self.can_see(a, game_map)
        ]

    def flee_from(self, predator: Animal, dt: float):
        self.is_fleeing = True
        dx = self.coordinate[0] - predator.coordinate[0]
        dy = self.coordinate[1] - predator.coordinate[1]
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            dx, dy = random.uniform(-1, 1), random.uniform(-1, 1)
            dist = 1.0
        flee_x = self.coordinate[0] + dx / dist * 200
        flee_y = self.coordinate[1] + dy / dist * 200
        self.move(dt, (flee_x, flee_y), self.flee_speed_mul)
        self.use_stamina(10.0 * dt)

    def try_hide(self, game_map, predator: "Predator") -> bool:
        dx = self.coordinate[0] - predator.coordinate[0]
        dy = self.coordinate[1] - predator.coordinate[1]
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            flee_angle = 0.0
        else:
            flee_angle = math.atan2(dy, dx)

        HIDE_ANGLE_LIMIT = math.radians(60)

        candidates = []
        for tree in game_map.trees:
            if tree.broken:
                continue
            tx, ty = tree.coordinate
            tree_dist = self.distance_to((tx, ty))
            if tree_dist > self.hide_range:
                continue
            angle_to_tree = math.atan2(ty - self.coordinate[1],
                                       tx - self.coordinate[0])
            if abs(_angle_diff(flee_angle, angle_to_tree)) <= HIDE_ANGLE_LIMIT:
                candidates.append((tree, tree_dist))

        if not candidates:
            return False

        best_tree, _ = min(candidates, key=lambda x: x[1])
        size_bonus = (best_tree.width_tiles * best_tree.height_tiles - 4) * 0.05
        final_rate = min(0.95, self.hide_success_rate + size_bonus)

        if random.random() < final_rate:
            self.is_hiding = True
            self._hiding_from = predator
            self.stop()
            if hasattr(predator, 'stop_hunt'):
                predator.stop_hunt()
            return True

        return False

    def stop_hiding(self):
        self.is_hiding = False
        self._hiding_from = None

    def stop_fleeing(self):
        self.is_fleeing = False

    def update(self, dt: float, game_map, weather, animals: List[Animal]):
        super().update(dt, game_map, weather, animals)
        if not self.alive or self.is_stunned:
            return

        if self.is_hiding:
            if (self._hiding_from is None
                    or not self._hiding_from.alive
                    or self.distance_to(self._hiding_from) > self.danger_range):
                self.stop_hiding()
            return

        predators = self.detect_predators(animals, game_map)

        if predators:
            self.predator_detected = True
            closest = min(predators, key=lambda p: self.distance_to(p))

            if self.distance_to(closest) < self.danger_range * 0.5:
                self.stop_fleeing()
                self.flee_from(closest, dt)
            else:
                if not self.try_hide(game_map, closest):
                    self.flee_from(closest, dt)
        elif self.is_seeking_water and self._water_target:
            self.predator_detected = False
            self.stop_fleeing()
            self.move(dt, self._water_target)
        else:
            self.predator_detected = False
            self.stop_fleeing()
            self.move(dt)
