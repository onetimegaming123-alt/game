import pygame
import sys
import time

pygame.init()

# екран
WIDTH, HEIGHT = 600, 400
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pixel Dance")

clock = pygame.time.Clock()

# кольори
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BLUE = (80, 160, 255)

# позиція персонажа
x = WIDTH // 2
y = HEIGHT // 2

frame = 0

def draw_dancer(x, y, frame):
    # тіло (піксельний стиль)
    pygame.draw.rect(screen, BLUE, (x, y, 20, 40))  # тулуб

    # голова
    pygame.draw.rect(screen, BLUE, (x, y - 20, 20, 20))

    # ноги (анімація)
    if frame % 2 == 0:
        pygame.draw.line(screen, BLUE, (x, y + 40), (x - 10, y + 70), 4)
        pygame.draw.line(screen, BLUE, (x + 20, y + 40), (x + 30, y + 70), 4)
    else:
        pygame.draw.line(screen, BLUE, (x, y + 40), (x + 10, y + 70), 4)
        pygame.draw.line(screen, BLUE, (x + 20, y + 40), (x + 10, y + 70), 4)

    # руки (анімація)
    if frame % 2 == 0:
        pygame.draw.line(screen, BLUE, (x, y + 10), (x - 20, y + 30), 4)
        pygame.draw.line(screen, BLUE, (x + 20, y + 10), (x + 40, y + 30), 4)
    else:
        pygame.draw.line(screen, BLUE, (x, y + 10), (x + 20, y + 30), 4)
        pygame.draw.line(screen, BLUE, (x + 20, y + 10), (x, y + 30), 4)


while True:
    screen.fill(BLACK)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

    draw_dancer(x, y, frame)

    frame += 1

    pygame.display.flip()
    clock.tick(5)  # швидкість "танцю"