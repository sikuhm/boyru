import pygame
import sys
import random #내가 추가
from map_system import GameMap, TILE_SIZE
from camera import Camera
from weather import WeatherSystem
from gui import HUD
from physics import PhysicsEngine
from Lee_animals import Parrot, Capybara, Monkey #내가 추가
from Choi_animals import Rhino, ElectricEel, ToxicFrog #내가 추가
from Bae import Anaconda, Crocodile, Tarantula #내가 추가

SCREEN_WIDTH  = 1280
SCREEN_HEIGHT = 720
FPS           = 60
TITLE         = "밀림의 왕자 보이루 - 아마존 생태계 시뮬레이터"

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()

    print("=== 밀림의 왕자 보이루 ===")
    print("[맵 생성 중... 잠시만 기다려주세요]")

    game_map = GameMap(map_width=180, map_height=135)
    print(f"맵 생성 완료: 나무 {len(game_map.trees)}개, "
          f"둥지 {sum(1 for t in game_map.trees if t.has_nest)}개")

    camera  = Camera(SCREEN_WIDTH, SCREEN_HEIGHT,
                     game_map.pixel_width, game_map.pixel_height)
    weather = WeatherSystem(SCREEN_WIDTH, SCREEN_HEIGHT)
    hud     = HUD(SCREEN_WIDTH, SCREEN_HEIGHT)
    physics = PhysicsEngine()

    animals = []
    eggs = []
    show_fov = False
    
    #내가 추가
    animals.append(Rhino(name="대장코뿔소", coordinate=(400.0, 500.0)))
    animals.append(ToxicFrog(name="화살독개구리", coordinate=(350.0, 450.0)))
    # 맵 전체에서 물 타일을 수집한 뒤, 그 중 랜덤 위치에 아나콘다 스폰
    water_tiles = [
        (tx, ty)
        for ty in range(game_map.map_height)
        for tx in range(game_map.map_width)
        if game_map.is_water(tx, ty)
    ]
    print(f"물 타일 {len(water_tiles)}개 발견")

    for i in range(11):
        if not water_tiles:
            break
        tx, ty = random.choice(water_tiles)
        px = tx * TILE_SIZE + TILE_SIZE / 2   # 타일 → 픽셀(중심) 변환
        py = ty * TILE_SIZE + TILE_SIZE / 2
        animals.append(Anaconda(name=f"아나콘다_{i+1}", coordinate=(px, py)))
        
    # 악어 — 아나콘다처럼 물에서 스폰
    for i in range(4):
        if not water_tiles:
            break
        tx, ty = random.choice(water_tiles)
        px = tx * TILE_SIZE + TILE_SIZE / 2
        py = ty * TILE_SIZE + TILE_SIZE / 2
        croc_sex = "male" if i % 2 == 0 else "female"
        animals.append(Crocodile(name=f"악어_{i+1}", coordinate=(px, py),
                             age=600, sex=croc_sex))
    # 전기뱀장어는 물 타일 근처에 스폰하는 것이 자연스럽습니다.
    animals.append(ElectricEel(name="전기뱀장어A", coordinate=(1000.0, 1000.0)))
    animals.append(ElectricEel(name="전기뱀장어B", coordinate=(1080.0,1000.0),sex='female'))
    animals.append(Capybara(name="카피바라A", coordinate=(1100.0, 1100.0)))
    animals.append(Monkey(name="원숭이A", coordinate=(1200.0, 1200.0)))
    animals.append(Parrot(name="앵무새A", coordinate=(1300.0, 1300.0)))

    animals.append(Rhino(name="대장코뿔소", coordinate=(400.0, 500.0), age=600, sex="male"))
    animals.append(ToxicFrog(name="화살독개구리", coordinate=(350.0, 450.0), age=600, sex="female"))
    # 육지 타일 수집 (한 번만)
    land_tiles = [
        (tx, ty)
        for ty in range(game_map.map_height)
        for tx in range(game_map.map_width)
        if not game_map.is_water(tx, ty)
    ]

    # 타란튤라 — 육지에서 스폰
    for i in range(4):
        if not land_tiles:
            break
        tx, ty = random.choice(land_tiles)
        px = tx * TILE_SIZE + TILE_SIZE / 2
        py = ty * TILE_SIZE + TILE_SIZE / 2
        tarantula_sex = "male" if i % 2 == 0 else "female"
        animals.append(Tarantula(name=f"타란튤라_{i+1}", coordinate=(px, py),
                             age=600, sex=tarantula_sex))

    # ... (중략) ...

    # 아나콘다 암수 교대로 생성
    for i in range(11):
        if not water_tiles:
            break
        tx, ty = random.choice(water_tiles)
        px = tx * TILE_SIZE + TILE_SIZE / 2
        py = ty * TILE_SIZE + TILE_SIZE / 2
        anaconda_sex = "male" if i % 2 == 0 else "female"
        animals.append(Anaconda(name=f"아나콘다_{i+1}", coordinate=(px, py), age=600, sex=anaconda_sex))
        
    animals.append(ElectricEel(name="전기뱀장어A", coordinate=(1000.0, 1000.0), age=600, sex="male"))
    animals.append(ElectricEel(name="전기뱀장어B", coordinate=(1080.0, 1000.0), age=600, sex='female'))
    
    # 홀로 외롭던 피식자들의 동반자 스폰 및 나이 설정
    animals.append(Capybara(name="카피바라A", coordinate=(1100.0, 1100.0), age=600, sex="male"))
    animals.append(Capybara(name="카피바라B", coordinate=(1150.0, 1100.0), age=600, sex="female"))
    
    animals.append(Monkey(name="원숭이A", coordinate=(1200.0, 1200.0), age=600, sex="male"))
    animals.append(Monkey(name="원숭이B", coordinate=(1250.0, 1200.0), age=600, sex="female"))
    
    animals.append(Parrot(name="앵무새A", coordinate=(1300.0, 1300.0), age=600, sex="male"))
    animals.append(Parrot(name="앵무새B", coordinate=(1350.0, 1300.0), age=600, sex="female"))

    # 독개구리들도 암수 분배
    for i in range(5):
        rx = random.uniform(500.0, 1500.0)
        ry = random.uniform(500.0, 1500.0)
        frog_sex = "male" if i % 2 == 0 else "female"
        animals.append(ToxicFrog(name=f"독개구리_{i+1}", coordinate=(rx, ry), age=600, sex=frog_sex))

    # 2. 반복문을 이용해 여러 마리를 랜덤 위치에 대량 스폰하기
    for i in range(5):
        # 안전하게 맵 중앙 부근(500 ~ 1500 픽셀 사이)에 랜덤 배치
        rx = random.uniform(500.0, 1500.0)
        ry = random.uniform(500.0, 1500.0)
        animals.append(ToxicFrog(name=f"독개구리_{i+1}", coordinate=(rx, ry)))
        
    for i in range(2):
        rx = 600.0 + i*50.0
        ry = 600.0 + i*50.0
        animals.append(Rhino(name=f"돌진코뿔소_{i+1}", coordinate=(rx, ry),sex=['male', 'female'][i%2]))

    print("모든 시스템 초기화 완료!")
    print("WASD 이동 | 마우스 휠 줌 | [ ] 시간 배속 조절")
    #내가 추가한 부분 끝

    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        # ── 이벤트 처리 ──
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    hud.selected_animal = None
                    hud.selected_tree   = None

                elif event.key == pygame.K_LEFTBRACKET:   # [ 키: 시간 느리게
                    weather.adjust_time_speed(-1)

                elif event.key == pygame.K_RIGHTBRACKET:  # ] 키: 시간 빠르게
                    weather.adjust_time_speed(1)

                elif event.key == pygame.K_F1:
                    print("[맵 재생성 중...]")
                    game_map = GameMap(map_width=180, map_height=135)
                    camera   = Camera(SCREEN_WIDTH, SCREEN_HEIGHT,
                                      game_map.pixel_width, game_map.pixel_height)
                    hud.selected_animal = None
                    hud.selected_tree   = None
                    print("맵 재생성 완료")

                elif event.key == pygame.K_F2:
                    weather._change_weather()

                elif event.key == pygame.K_F3:
                    if hud.selected_tree and not hud.selected_tree.broken:
                        game_map.break_tree(hud.selected_tree)
                        print("나무 파괴 테스트!")

                elif event.key == pygame.K_F4:
                    show_fov = not show_fov
                    print(f"시야 표시 {'ON' if show_fov else 'OFF'}")

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # 좌클릭
                    mx, my = event.pos
                    
                    # 💡 [추가] gui.py에 정의된 미니맵 위치와 크기 (우측 하단)
                    mm_x = SCREEN_WIDTH - 210
                    mm_y = SCREEN_HEIGHT - 160
                    mm_w = 200
                    mm_h = 150

                    # 1. 클릭한 좌표가 미니맵 내부인지 확인
                    if mm_x <= mx <= mm_x + mm_w and mm_y <= my <= mm_y + mm_h:
                        # 미니맵 내 클릭 위치를 0.0 ~ 1.0 비율로 계산
                        ratio_x = (mx - mm_x) / mm_w
                        ratio_y = (my - mm_y) / mm_h
                        
                        # 게임 맵 전체 픽셀 크기에 비율을 곱해 실제 월드 좌표 획득
                        target_world_x = ratio_x * game_map.pixel_width
                        target_world_y = ratio_y * game_map.pixel_height
                        
                        # 카메라 포커스 이동 (camera.py의 focus_on 메서드 활용)
                        camera.focus_on(target_world_x, target_world_y)
                        print(f"미니맵 이동: ({target_world_x:.0f}, {target_world_y:.0f})")
                        
                    # 2. 미니맵 밖을 클릭했다면 기존의 동물/나무 정보 보기 로직 실행
                    else:
                        wx, wy = camera.screen_to_world(mx, my)
                        hud.handle_click(wx, wy, animals, game_map)

            elif event.type == pygame.MOUSEWHEEL:
                camera.handle_zoom(event.y, pygame.mouse.get_pos())

        # ── 업데이트 ──
        keys = pygame.key.get_pressed()
        
        # 카메라는 현실 시간에 맞춰 부드럽게 이동해야 하므로 원래 dt 사용
        camera.update(dt, keys)
        # 날씨 시스템은 내부적으로 시계에 배속을 계산하고 있으므로 원래 dt 사용
        weather.update(dt)

        # 💡 [핵심 수정] 동물들에게 적용될 '게임 내 시간(game_dt)'을 계산
        game_dt = dt * weather.time_speed

        for animal in animals:
            if hasattr(animal, 'update'):
                # 기존의 dt 대신 배속이 곱해진 game_dt를 넘겨줌!
                animal.update(game_dt, game_map, weather, animals)
            # ✨ [추가] 동물이 품고 있는 새 생명이 있다면 꺼내옵니다.
            if getattr(animal, 'pending_child', None) is not None:
                child = animal.pending_child
                if type(child).__name__ == "Egg":
                    eggs.append(child)  # 알이면 부화기에 넣기
                else:
                    animals.append(child) # 코뿔소 같은 태생이면 바로 필드에 추가
                animal.pending_child = None
        
        # ✨ [추가] 2. 알 부화 관리
        for egg in eggs[:]:
            hatched_animal = egg.update(game_dt)
            if hatched_animal:  # 알이 부화했다면!
                animals.append(hatched_animal)
                eggs.remove(egg)

        for animal in animals:
            if hasattr(animal, 'update'):
                animal.update(dt, game_map, weather, animals)

        if animals:
            physics.apply_separation(animals)
            for animal in animals:
                if hasattr(animal, 'coordinate'):
                    animal.coordinate = list(physics.keep_in_bounds(
                        animal.coordinate,
                        game_map.pixel_width, game_map.pixel_height
                    )) #list() 추가

        # ── 렌더링 ──
        screen.fill((15, 30, 15))
        game_map.draw(screen, camera.x, camera.y,
                      SCREEN_WIDTH, SCREEN_HEIGHT, camera.zoom)
        
        # ✨ [추가] 필드에 놓인 알 그리기
        for egg in eggs:
            egg.draw(screen, camera)

        for animal in animals:
            if hasattr(animal, 'draw'):
                animal.draw(screen, camera)
        
        # system.py의 하단 렌더링 파트를 찾아 아래처럼 수정합니다.
        if show_fov:
            for animal in animals:
                if hasattr(animal, 'draw_fov_debug'):
                    # 💡 [수정] color 매개변수를 지워서 animal.py에서 정의한 고유 색상이 나오게 합니다.
                    animal.draw_fov_debug(screen, camera, alpha=80)

        weather.draw(screen)
        hud.draw(screen, weather, camera, game_map, animals)

        fps_surf = pygame.font.SysFont("consolas", 14).render(
            f"FPS: {clock.get_fps():.1f}", True, (200, 200, 200)
        )
        screen.blit(fps_surf, (SCREEN_WIDTH - 90, 52))

        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()