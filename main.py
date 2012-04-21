import sys, pygame, spritesheet, wordwrap

WIDTH = HEIGHT = 300
TILE_SIZE = 20
VISIBLE_MAP_SIZE = 10
CHAR_XY = WIDTH / 2
GRAVITY = 2
MAP_SIZE_TILES = 20
MAP_SIZE_PIXELS = MAP_SIZE_TILES * TILE_SIZE

DEBUG = True

screen = pygame.display.set_mode((WIDTH, HEIGHT))

def get_uid():
  get_uid.uid += 1
  return get_uid.uid
get_uid.uid = 0


class Point:
  def __init__(self, x, y):
    self.x = x
    self.y = y

  def __cmp__(self, other):
    return 0 if self.x == other.x and self.y == other.y else 1

  def __str__(self):
    return "<Point x : %f y : %f>" % (self.x, self.y)

class TileSheet:
  """ Memoize all the sheets so we don't load in 1 sheet like 50 times and
  squander resources. This is a singleton, which is generally frowned upon,
  but I think it's okay here."""
  sheets = {}

  @staticmethod
  def add(file_name):
    if file_name in TileSheet.sheets:
      return

    new_sheet = spritesheet.spritesheet(file_name)
    width, height = dimensions = new_sheet.sheet.get_size()
    TileSheet.sheets[file_name] =\
     [[new_sheet.image_at((x, y, TILE_SIZE, TILE_SIZE), colorkey=(255,255,255))\
       for y in range(0, height, TILE_SIZE)] for x in range(0, width, TILE_SIZE)]

  @staticmethod
  def get(sheet, x, y):
    if sheet not in TileSheet.sheets:
      TileSheet.add(sheet)
    return TileSheet.sheets[sheet][x][y]

#TODO: Entity should extend Rect.

class Rect(object):
  def __init__(self, x, y, s):
    self.x = x
    self.y = y
    self.size = s

  def touches_point(self, point):
    return self.x <= point.x <= self.x + self.size and\
           self.y <= point.y <= self.y + self.size

class Entity(object):
  def __init__(self, x, y, groups, src_x = -1, src_y = -1, src_file = ""):
    self.x = x
    self.y = y
    self.size = TILE_SIZE

    if src_x != -1 and src_y != -1:
      self.img = TileSheet.get(src_file, src_x, src_y)
      self.rect = self.img.get_rect()

    self.uid = get_uid()
    self.events = {}
    self.groups = groups

  def nicer_rect(self):
    return Rect(self.x, self.y , self.size)

  def touches_point(self, point):
    return self.x <= point.x <= self.x + self.size and\
           self.y <= point.y <= self.y + self.size

  def touches_rect(self, other):
    if hasattr(self, 'uid') and hasattr(other, 'uid') and self.uid == other.uid: return False

    return self.x < other.x + other.size and \
           self.x + self.size > other.x and \
           self.y < other.y + other.size and \
           self.y + self.size > other.y

  def add_group(self, group):
    self.groups.append(group)

  # Add and remove callbacks

  def on(self, event, callback):
    if event in self.events:
      self.events[event].append(callback)
    else:
      self.events[event] = [callback]

  def off(self, event, callback = None):
    if callback is None:
      self.events[event] = []
    else:
      self.events[event].remove(callback)

  def emit(self, event):
    for callback in self.events:
      callback()

  # How high/low this object is
  def depth(self):
    return 0

  # Methods that must be implemented if you extend Entity
  def groups(self):
    return groups

  def render(self, screen, dx=0, dy=0):
    self.rect.x = self.x + dx
    self.rect.y = self.y + dy
    screen.blit(self.img, self.rect)

  def update(self, entities):
    raise "UnimplementedUpdateException"

class Tile(Entity):
  def __init__(self, x, y, tx, ty):
    super(Tile, self).__init__(x, y, ["renderable", "updateable", "relative"], tx, ty, "tiles.png")

  def update(self, entities):
    pass

def isalambda(v):
  return isinstance(v, type(lambda: None)) and v.__name__ == '<lambda>'

class Entities:
  def __init__(self):
    self.entities = []
    self.entityInfo = []

  def add(self, entity):
    self.entities.append(entity)

  def elem_matches_criteria(self, elem, *criteria):
    for criterion in criteria:
      if isinstance(criterion, basestring):
        if criterion not in elem.groups:
          return False
      elif isalambda(criterion):
        if not criterion(elem):
          return False
      else:
        raise "UnsupportedCriteriaType"

    return True

  def get(self, *criteria):
    results = []

    for entity in self.entities:
      if self.elem_matches_criteria(entity, *criteria):
        results.append(entity)

    return results

  def one(self, *criteria):
    results = self.get(*criteria)
    assert len(results) == 1
    return results[0]

  def any(self, *criteria):
    return len(self.get(*criteria)) > 0

  def remove_all(self, *criteria):
    retained = []

    for entity in self.entities:
      if not self.elem_matches_criteria(entity, *criteria):
        retained.append(entity)

    self.entities = retained

def tupleize(color):
  return (color.r, color.g, color.b)

class Map(Entity):
  def __init__(self):
    self.full_map_size = 20
    self.mapx = 0
    self.mapy = 0
    self.visible_map_size = VISIBLE_MAP_SIZE

    super(Map, self).__init__(0, 0, ["updateable", "map"])

  def update(self, entities):
    pass

  def new_map_rel(self, entities, dx, dy):
    self.new_map_abs(entities, self.mapx + dx, self.mapy + dy)

  def new_map_abs(self, entities, x, y):
    self.mapx = x
    self.mapy = y
    entities.remove_all("map_element")

    self.mapdata = TileSheet.get('map.png', self.mapx, self.mapy)

    mapping = { (0, 0, 0): 1
              , (255, 255, 255): 0
              }

    for i in range(MAP_SIZE_TILES):
      for j in range(MAP_SIZE_TILES):
        colors = mapping[tupleize(self.mapdata.get_at((i, j)))]

        if colors == 0:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
        elif colors == 1:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 1, 0)
          tile.add_group("wall")

        tile.add_group("map_element")
        entities.add(tile)

class UpKeys:
  """ Simple abstraction to check for recent key released behavior. """
  keysup = []
  keysactive = []

  @staticmethod
  def flush():
    UpKeys.keysup = []

  @staticmethod
  def add_key(val):
    UpKeys.keysup.append(val)
    UpKeys.keysactive.append(val)

  # This is a setter.
  @staticmethod
  def release_key(val):
    if val in UpKeys.keysactive:
      UpKeys.keysactive.remove(val)

  @staticmethod
  def key_down(val):
    return val in UpKeys.keysactive

  @staticmethod
  def key_up(val):
    if val in UpKeys.keysup:
      UpKeys.keysup.remove(val)
      return True
    return False

def sign(a):
  if a > 0: return 1
  if a < 0: return -1
  return 0

class Character(Entity):
  def __init__(self, x, y):
    super(Character, self).__init__(x, y, ["renderable", "updateable", "character", "relative"], 0, 1, "tiles.bmp")
    self.speed = 5
    self.vy = 0
    self.onground = False

  def collides_with_wall(self, entities):
    nr = self.nicer_rect()
    return entities.any("wall", lambda x: x.touches_rect(nr))

  def check_new_map(self, entities):
    m = entities.one("map")
    d = (0, 0)

    if self.x + self.size > MAP_SIZE_PIXELS: d = (1, 0)
    if self.x < 0: d = (-1, 0)
    if self.y + self.size > MAP_SIZE_PIXELS: d = (0, 1)
    if self.y < 0: d = (0, -1)

    if d != (0, 0):
      m.new_map_rel(entities, *d)

      self.x -= (MAP_SIZE_PIXELS - TILE_SIZE) * d[0]
      self.y -= (MAP_SIZE_PIXELS - TILE_SIZE) * d[1]

  def update(self, entities):
    dx, dy = (0, 0)

    if UpKeys.key_down(pygame.K_LEFT): dx -= self.speed
    if UpKeys.key_down(pygame.K_RIGHT): dx += self.speed
    if UpKeys.key_down(pygame.K_SPACE): dy = -20

    self.vy -= GRAVITY
    dy -= self.vy
    dy = min(dy, 5)

    delta = .1
    dest_x = self.x + dx
    dest_y = self.y + dy

    self.x += dx
    while self.collides_with_wall(entities):
      self.x -= sign(dx) or -1

    self.y += dy
    while self.collides_with_wall(entities):
      self.y -= sign(dy) or -1

    self.onground = False

    for p in zip(range(self.x + 2, self.x + self.size - 2), [self.y + self.size + 1] * self.size):
      if entities.any("wall", lambda x: x.touches_point(Point(*p))):
        self.onground = True
        break

    if self.onground:
      dy = 0
      self.vy = 0

    self.check_new_map(entities)

def render_all(manager):
  ch = manager.one("character")
  x_ofs = max(min(ch.x, 400 - CHAR_XY), CHAR_XY)
  y_ofs = max(min(ch.y, 400 - CHAR_XY), CHAR_XY)

  for e in manager.get("renderable"):
    e.render(screen, CHAR_XY-x_ofs, CHAR_XY-y_ofs)

def main():
  manager = Entities()
  manager.add(Character(40, 40))

  m = Map()
  m.new_map_abs(manager, 0, 0)
  manager.add(m)

  pygame.display.init()
  pygame.font.init()

  if not DEBUG:
    pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
    pygame.mixer.music.load('ludumherp.mp3')
    pygame.mixer.music.play(-1) #Infinite loop! HAHAH!

  while True:
    for event in pygame.event.get():
      UpKeys.flush()
      if event.type == pygame.QUIT:
        pygame.quit()
        sys.exit()
      if event.type == pygame.KEYDOWN:
        UpKeys.add_key(event.key)
      if event.type == pygame.KEYUP:
        UpKeys.release_key(event.key)

    if UpKeys.key_down(113) and UpKeys.key_down(310): # Q and CMD
      break

    for e in manager.get("updateable"):
      e.update(manager)

    screen.fill((255, 255, 255))

    render_all(manager)

    pygame.display.flip()


main()
