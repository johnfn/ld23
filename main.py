from __future__ import division
import sys, pygame, spritesheet, wordwrap
import random
import numpy
import math
from wordwrap import render_textrect

WIDTH = HEIGHT = 300
TILE_SIZE = 20
VISIBLE_MAP_SIZE = 10
CHAR_XY = WIDTH / 2
GRAVITY = 2
MAP_SIZE_TILES = 20
MAP_SIZE_PIXELS = MAP_SIZE_TILES * TILE_SIZE
NOT_DARK = 0

#aesthestics

JIGGLE_LENGTH = 50
JIGG_RANGE = 3

#gameplay

MAX_HEALTH_INC = 3
INSANE_LIGHT = 150

#depths

LIGHT_DEPTH = 2
LIGHT_SOURCE_DEPTH = 5
PARTICLE_DEPTH = 10
BULLET_DEPTH = 50
CHAR_DEPTH = 80
TEXT_DEPTH = 100
BAR_DEPTH = 200

DEBUG = True

screen = pygame.display.set_mode((WIDTH, HEIGHT))

def get_uid():
  get_uid.uid += 1
  return get_uid.uid
get_uid.uid = 0

def darken(surface, value):
    "Value is 0 to 255. So 128 would be 50% darken"
    dark = pygame.Surface(surface.get_size(), 32)
    dark.set_alpha(value, pygame.RLEACCEL)
    surface.blit(dark, (0, 0))

def blur_surf(surface, amt):
    if amt < 1.0: raise ValueError("Arg 'amt' must be greater than 1.0, passed in value is %s"%amt)

    scale = 1.0/float(amt)
    surf_size = surface.get_size()
    scale_size = (int(surf_size[0]*scale), int(surf_size[1]*scale))
    surf = pygame.transform.smoothscale(surface, scale_size)
    surf = pygame.transform.smoothscale(surf, surf_size)
    return surf


class Tick:
  tick = 0

  @staticmethod
  def inc():
    Tick.tick += 1

  @staticmethod
  def get(prob=1):
    return (Tick.tick % prob == 0)

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
    return self.x <= point[0] <= self.x + self.size and\
           self.y <= point[1] <= self.y + self.size

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
    self.visible = True

    self.jiggling = 0
    self.old_xy = ()
    self.flashing = 0

  def jiggle(self):
    self.jiggling = JIGGLE_LENGTH
    self.old_xy = (self.x, self.y)

  def collides_with_wall(self, entities):
    nr = self.nicer_rect()
    return entities.any("wall", lambda x: x.touches_rect(nr))

  def nicer_rect(self):
    return Rect(self.x, self.y , self.size)

  def touches_point(self, point):
    return self.x <= point[0] <= self.x + self.size and\
           self.y <= point[1] <= self.y + self.size

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
  # Big = on top.
  def depth(self):
    return 0

  def groups(self):
    return groups

  def is_jiggling(self):
    return self.jiggling > 0

  def is_flashing(self):
    return self.flashing > 0

  def flash(self):
    self.flashing = 30

  def render(self, screen, dx=0, dy=0):
    if not self.visible: return

    self.rect.x = self.x + dx
    self.rect.y = self.y + dy

    screen.blit(self.img, self.rect)

  def update(self, entities):
    if self.jiggling > 0:
      self.x = self.x + random.randrange(-JIGG_RANGE, JIGG_RANGE)
      self.y = self.y + random.randrange(-JIGG_RANGE, JIGG_RANGE)
      self.jiggling -= 1

    if self.flashing > 0:
      #TODO: Add flashing stuff here.

      self.flashing -= 1

class Particles(Entity):
  def __init__(self, entities, particle_sources):
    self.surf = pygame.Surface((MAP_SIZE_PIXELS, MAP_SIZE_PIXELS), pygame.SRCALPHA) #TODO: make actual map size.

    super(Particles, self).__init__(0, 0, ["renderable", "updateable", "relative", "particles"])
    self.particles = []
    self.beams = []
    self.particle_sources = particle_sources
    self.tick = 0

  def update(self, entities):
    self.tick += 1
    self.surf = pygame.Surface((MAP_SIZE_PIXELS, MAP_SIZE_PIXELS), pygame.SRCALPHA) #TODO: make actual map size.

    for source in self.particle_sources:
      if random.random() > .8:
        p = Particle(source.x, source.y)
        self.particles.append(p)
        entities.add(p)

        if len(self.particles) > 20:
          removed = random.choice(self.particles)
          self.particles.remove(removed)
          entities.remove(removed)

    for p in self.particles:
      p.update()
      p.render(self.surf)

    self.surf = blur_surf(self.surf, 5.0)

  def depth(self):
    return PARTICLE_DEPTH

  def render(self, screen, dx, dy):
    #screen.blit(self.surf, self.surf.get_rect().topleft)
    screen.blit(self.surf, (dx, dy))

class Particle(Entity):
  def __init__(self, x, y):
    self.x = x
    self.x_init = x
    self.y = y
    self.speed = random.random() * 2 + 0.4
    self.tick = 0
    self.sin_width = random.random() * 25 + 3
    self.sin_offset = random.random() * 5 + 5
    self.sin_speed = random.random() / 3

    super(Particle, self).__init__(x, y, [], 7, 0, "tiles.png")
    self.trans_img = self.img.copy()
    self.trans_img.set_colorkey((0, 0, 0))

    # force start at source
    first_x = self.x_init + math.sin(self.sin_offset + self.sin_speed * self.tick/10) * self.sin_width
    diff_x = self.x - first_x
    self.x_init = self.x_init + diff_x
    self.x = self.x_init

  def update(self):
    self.tick += 1
    self.y -= self.speed
    self.x = self.x_init + math.sin(self.sin_offset + self.sin_speed * self.tick/10) * self.sin_width

  def render(self, screen):
    screen.blit(self.trans_img, (self.x, self.y))

class LightBeam(Entity):
  def __init__(self, x, y):
    super(LightBeam, self).__init__(x, y, [], 8, 0, "tiles.png")
    self.img.set_alpha(50)

class LightSpot(Entity):
  def __init__(self, x, y, intensity):
    if intensity > 200: intensity = 200

    self.x = x
    self.y = y

    self.s = pygame.Surface((TILE_SIZE,TILE_SIZE), pygame.SRCALPHA)  # the size of your rect
    self.s.fill((0, 0, 0, intensity))

  def render(self, screen):
    screen.blit(self.s, (self.x, self.y))

# ALL the light in the game. ALL OF IT. Make it blurry, yo. Beacon it up in here. LOL BEACON? I DONT KNOW WHAT BEACON IS. ISNT THAT A CRISPY BREAKFAST FOOD? IVE NEVER HEARD OF IT LOL.
class Light(Entity):
  def __init__(self, dark_values, light_objs):
    #TODO: constants.

    self.light_objs = light_objs
    self.dark_values = dark_values

    self.recalculate_light()

    super(Light, self).__init__(0, 0, ["renderable", "relative", "all-lights"], 5, 0, "tiles.png")

  def depth(self):
    return LIGHT_DEPTH

  def recalculate_light(self):
    self.surf = pygame.Surface((MAP_SIZE_PIXELS, MAP_SIZE_PIXELS), pygame.SRCALPHA) #TODO: make actual map size.

    # calculate ambient light of each (x,y) position.
    self.spots = [[None for x in range(MAP_SIZE_TILES)] for y in range(MAP_SIZE_TILES)]
    for x in range(MAP_SIZE_TILES):
      for y in range(MAP_SIZE_TILES):
        self.spots[x][y] = LightSpot(x * TILE_SIZE, y * TILE_SIZE, self.dark_values[x][y])

    # build an array of every beam object created by every light.
    self.beams = []

    for source in self.light_objs:
      if "beamlight" in source.groups:
        for beam_pos in source.light_beam_pos():
          print beam_pos
          self.beams.append(LightBeam(beam_pos[0], beam_pos[1]))

    for x in range(MAP_SIZE_TILES):
      for y in range(MAP_SIZE_TILES):
        self.spots[x][y].render(self.surf)

    self.surf = blur_surf(self.surf, 15.0)

    for beam in self.beams:
      beam.render(self.surf)

    self.surf = blur_surf(self.surf, 10.0)

  def render(self, screen, dx, dy):
    #screen.blit(self.surf, self.surf.get_rect().topleft)
    screen.blit(self.surf, (dx, dy))


class Tile(Entity):
  def __init__(self, x, y, tx, ty):
    super(Tile, self).__init__(x, y, ["renderable", "updateable", "relative"], tx, ty, "tiles.png")

  def update(self, entities):
    super(Tile, self).update(entities)

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

  def remove(self, obj):
    self.entities = [e for e in self.entities if e.uid != obj.uid]

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
    self.full_map_size = MAP_SIZE_TILES
    self.mapx = 0
    self.mapy = 0
    self.visible_map_size = VISIBLE_MAP_SIZE
    self.light_deltas = None

    super(Map, self).__init__(0, 0, ["updateable", "map"])

  def update(self, entities):
    super(Map, self).update(entities)

  def new_map_rel(self, entities, dx, dy):
    self.new_map_abs(entities, self.mapx + dx, self.mapy + dy)

  def in_bounds(self, point):
    return point[0] >= 0 and point[1] >= 0 and point[0] < MAP_SIZE_PIXELS and point[1] < MAP_SIZE_PIXELS

  def new_map_abs(self, entities, x, y):
    self.mapx = x
    self.mapy = y
    entities.remove_all("map_element")

    self.mapdata = TileSheet.get('laderp.bmp', self.mapx, self.mapy)

    mapping = { (0, 0, 0): 1
              , (255, 255, 255): 0
              , (255, 0, 0): 2 #dumbEnemy
              , (0, 0, 255): 3 #light source
              , (100, 100, 100): 4 #reflector
              }

    self.tiles = [[None for i in range(MAP_SIZE_TILES)] for j in range(MAP_SIZE_TILES)]

    particle_sources = []
    light_sources = []

    for i in range(MAP_SIZE_TILES):
      for j in range(MAP_SIZE_TILES):
        colors = mapping[tupleize(self.mapdata.get_at((i, j)))]

        if colors == 0:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
        elif colors == 1:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 1, 0)
          tile.add_group("wall")
        elif colors == 2:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          entities.add(Enemy(i * TILE_SIZE, j * TILE_SIZE, Enemy.STRATEGY_STUPID))
        elif colors == 3:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          particle_sources.append([i * TILE_SIZE, j * TILE_SIZE])
          light_sources.append([i * TILE_SIZE, j * TILE_SIZE])
        elif colors == 4:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          entities.add(Reflector(i * TILE_SIZE, j * TILE_SIZE, None))

        tile.add_group("map_element")
        entities.add(tile)
        self.tiles[i][j] = tile

    self.calculate_lighting(light_sources, entities)

  def is_wall_rel(self, i, j):
    return "wall" in self.tiles[i][j].groups

  def get_lighting_rel(self, i, j):
    return self.light_deltas[i][j]

  def calculate_lighting(self, light_sources, entities):
    # everything starts dark.
    dark_values = [[255 for x in range(MAP_SIZE_TILES)] for y in range(MAP_SIZE_TILES)]
    light_objs = []

    # Sources need to be aware of the entire map, so we add them last.
    for source in light_sources:
      #TODO: Ther eis no differentiation between BEAM and RADIAL at this point.
      new_l = LightSource(source[0], source[1], entities, self, LightSource.BEAM)
      light_deltas = new_l.calculate_light_deltas(entities, self)
      for i, elem in enumerate(light_deltas):
        for j, delta in enumerate(elem):
          dark_values[i][j] += delta

          if dark_values[i][j] > 255: dark_values[i][j] = 255
          if dark_values[i][j] < 0: dark_values[i][j] = 0

      light_objs.append(new_l)
      entities.add(new_l)

    # the only things that generate particles currently are lights. thats why i pass in light_objs, not particle_objs.
    entities.add(Particles(entities, light_objs))
    entities.add(Light(dark_values, light_objs))
    self.light_deltas = dark_values


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

  @staticmethod
  def invalidate_key(val):
    if val in UpKeys.keysup: UpKeys.keysup.remove(val)

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

class Text(Entity):
  def __init__(self, follow, contents):
    UpKeys.invalidate_key(pygame.K_z)
    super(Text, self).__init__(follow.x, follow.y, ["renderable", "text", "updateable", "relative"])
    self.contents = contents
    self.follow = follow
    self.shown_chars = 1
    self.tot_chars = len(contents)

  def depth(self):
    return TEXT_DEPTH

  def update(self, entities):
    super(Text, self).update(entities)
    if UpKeys.key_up(pygame.K_z):
      if self.shown_chars == self.tot_chars:
        entities.remove(self)
      else:
        self.shown_chars = self.tot_chars

    if Tick.get(3) and self.shown_chars < self.tot_chars:
      self.shown_chars += 1

  def render(self, screen, dx, dy):
    if not self.visible: return

    my_width = 100
    my_font = pygame.font.Font("nokiafc22.ttf", 12)
    vis_text = self.contents[:self.shown_chars]

    my_rect = pygame.Rect((self.follow.x + dx - my_width / 2, self.follow.y + dy - len(vis_text) - 30, my_width, 70))
    if my_rect.x < 0:
      my_rect.x = 0
    rendered_text = render_textrect(vis_text, my_font, my_rect, (10, 10, 10), (255, 255, 255), False, 1)

    screen.blit(rendered_text, my_rect.topleft)

class Bar(Entity):
  def __init__(self, follow, color_health, color_no_health, amt, max_amt):
    super(Bar, self).__init__(follow.x, follow.y, ["renderable", "updateable", "healthbar", "relative"])
    self.amt = amt
    self.max_amt = max_amt
    self.color_health = color_health
    self.color_no_health = color_no_health
    self.follow = follow

    self.width = 40
    self.height = 8
    self.border_width = 2

  def set_amt(self, x):
    self.amt = x

  def set_max_amt(self, x):
    self.max_amt = x

  def depth(self):
    return BAR_DEPTH

  def update(self, entities):
    self.x = self.follow.x
    self.y = self.follow.y

    super(Bar, self).update(entities)

  def render(self, screen, dx, dy):
    if not self.visible: return

    # Outer border
    pygame.draw.rect(screen, (0, 0, 0), (self.x + dx, self.y + dy, self.width, self.height))

    # Inside
    actual_w = self.width - self.border_width * 2
    actual_h = self.height - self.border_width * 2
    pygame.draw.rect(screen, self.color_no_health, (self.x + self.border_width + dx, self.y + self.border_width + dy, actual_w, actual_h))

    # 'Health'
    health_w = (self.amt / self.max_amt) * actual_w
    pygame.draw.rect(screen, self.color_health, (self.x + self.border_width + dx, self.y + self.border_width + dy, health_w, actual_h))

class Reflector(Entity):
  def __init__(self, x, y, type):
    self.direction = [1, 0]
    super(Reflector, self).__init__(x, y, ["renderable", "reflector", "relative"], 6, 0, "tiles.png")

  def reflect(self, direction):
    return [direction[1], -direction[0]]

class Enemy(Entity):
  STRATEGY_STUPID = 0
  STRATEGY_SENTRY = 1
  hp = {STRATEGY_STUPID: 5}

  def __init__(self, x, y, type):
    self.speed = 3
    self.type = type
    self.hp = Enemy.hp[self.type]

    self.direction = [1, 0]
    super(Enemy, self).__init__(x, y, ["renderable", "updateable", "enemy", "relative", "map_element"], 4, 0, "tiles.png")

  def update(self, entities):
    super(Enemy, self).update(entities)

    if self.type == Enemy.STRATEGY_STUPID:
      self.be_stupid(entities)

    ch = entities.one("character")
    if self.touches_rect(ch):
      ch.hurt(1)

  def die(self, entities):
    entities.remove(self)

  def hurt(self, amt, entities):
    self.hp -= 1
    if self.hp <= 0:
      self.die(entities)

  def be_stupid(self, entities):
    self.x += self.direction[0]
    self.y += self.direction[1]

    if self.collides_with_wall(entities):
      self.direction[0] *= -1
      self.direction[1] *= -1

class LightSource(Entity):
  BEAM = 0
  RADIAL = 1

  def __init__(self, x, y, entities, m, light_type, dir=None):
    if dir is None:
      self.direction = (1, 0)
    else:
      self.direction = dir

    self.light_type = light_type
    self.intensity = -255
    self.falloff = 60
    self.lightbeampos = []

    super(LightSource, self).__init__(x, y, ["wall", "renderable", "relative", "updateable", "map_element", "lightsource"], 5, 0, "tiles.png")

    if light_type == LightSource.BEAM:
      self.groups.append("beamlight")
      self.groups.append("pushable")

    assert(self.x % TILE_SIZE == 0)
    assert(self.y % TILE_SIZE == 0)

  def push(self, direction, entities):
    new_x = self.x + direction[0] * TILE_SIZE
    new_y = self.y + direction[1] * TILE_SIZE

    if entities.any("wall", lambda e: e.x == new_x and e.y == new_y): return
    self.move(new_x, new_y, entities)

  def move(self, x, y, entities):
    self.x = x
    self.y = y

    entities.one("all-lights").recalculate_light()

  def calculate_light_deltas(self, entities, m):
    if self.light_type == LightSource.BEAM:
      return self.beam_deltas(entities, m)
    elif self.light_type == LightSource.RADIAL:
      return self.radial_deltas(entities, m)

  def radial_deltas(self, entities, m):
    radius = 500
    pts = []
    deltas = [[0 for x in range(MAP_SIZE_TILES)] for y in range(MAP_SIZE_TILES)]

    for x in range(self.x - radius, self.x + radius + 1, TILE_SIZE):
      for y in range(self.y - radius, self.y + radius + 1, TILE_SIZE):
        if x == self.x - radius or x == self.x + radius or y == self.y - radius or y == self.y + radius:
          pts.append((x, y))

    for x, y in pts:
      pt = [self.x, self.y]

      #raycast to (x, y) and light up everything along the way.
      dx = (x - self.x) / radius
      dy = (y - self.y) / radius

      for i in range(radius):
        if not m.in_bounds((pt[0], pt[1])): break
        if m.is_wall_rel(int(pt[0] / 20), int(pt[1] / 20)): break
        deltas[int(pt[0] / 20)][int(pt[1] / 20)] = self.intensity * (1 - (i + 20) / (radius + 20))
        pt[0] = pt[0] + dx
        pt[1] = pt[1] + dy

    return deltas

  def light_beam_pos(self):
    return self.lightbeampos

  def beam_deltas(self, entities, m):
    self.lightbeampos = []
    deltas = [[0 for x in range(MAP_SIZE_TILES)] for y in range(MAP_SIZE_TILES)]

    pos_abs = [self.x, self.y]
    pos_rel = [int(self.x / TILE_SIZE), int(self.y / TILE_SIZE)]
    cur_dir = self.direction

    while m.in_bounds(pos_abs) and not entities.any("wall", lambda e: e.x == pos_abs[0] and e.y == pos_abs[1] and e.uid != self.uid):
      # bugginess of this line approaches 1...
      deltas[pos_rel[0]][pos_rel[1]] = self.intensity
      self.lightbeampos.append((pos_abs[0], pos_abs[1]))

      # radial lighting
      radius = int(math.ceil(- self.intensity / self.falloff))

      for x in range(pos_rel[0] - radius, pos_rel[0] + radius + 1):
        for y in range(pos_rel[1] - radius, pos_rel[1] + radius + 1):
          if m.in_bounds((x * TILE_SIZE, y * TILE_SIZE)):
            point_intensity = -max(0, 255 - (abs(x - pos_rel[0]) + abs(y - pos_rel[1])) * self.falloff)
            deltas[x][y] += point_intensity

      if cur_dir[0] == 0 and cur_dir[1] == 0: break

      reflectors = entities.get("reflector", lambda e: e.x == pos_abs[0] and e.y == pos_abs[1])

      if len(reflectors) > 0:
        cur_dir = reflectors[0].reflect(cur_dir)

      pos_abs[0] += cur_dir[0] * TILE_SIZE
      pos_abs[1] += cur_dir[1] * TILE_SIZE

      pos_rel[0] += cur_dir[0]
      pos_rel[1] += cur_dir[1]

    return deltas

  def depth(self):
    return LIGHT_SOURCE_DEPTH

class Bullet(Entity):
  def __init__(self, owner, direction, dmg):
    self.speed = 6
    if "character" in owner.groups: self.speed = 10

    self.direction = direction
    self.owner = owner
    self.dmg = dmg
    super(Bullet, self).__init__(owner.x, owner.y, ["renderable", "updateable", "bullet", "relative", "map_element"], 3, 0, "tiles.png")

  def depth(self):
    return BULLET_DEPTH

  def update(self, entities):
    super(Bullet, self).update(entities)

    self.x += self.direction[0] * self.speed
    self.y += self.direction[1] * self.speed

    if not entities.one("map").in_bounds((self.x, self.y)):
      entities.remove(self)
      print "off"
      return

    hitlambda = lambda x: x.touches_point((self.x + self.size/2, self.y + self.size/2))

    walls_hit = entities.get("wall", hitlambda)
    if len(walls_hit) > 0:
      entities.remove(self)
      return

    enemies_hit = entities.get("enemy", hitlambda)
    if len(enemies_hit) > 0:
      entities.remove(self)
      enemies_hit[0].hurt(self.dmg, entities)
      return

class Character(Entity):
  def __init__(self, x, y, entities):
    super(Character, self).__init__(x, y, ["renderable", "updateable", "character", "relative"], 0, 1, "tiles.bmp")
    self.speed = 5
    self.vy = 0
    self.onground = False
    self.cooldown = 5
    self.direction = (1, 0)

    self.hp = 5
    self.max_hp = 5

    self.hp_bar = Bar(self, (0, 255, 0), (255, 0, 0), self.hp, self.max_hp)
    entities.add(self.hp_bar)
    self.hp_bar.visible = False

    self.sanity = 10
    self.max_sanity = 10

    self.sanity_bar = Bar(self, (255, 255, 255), (0, 0, 0), self.sanity, self.max_sanity)
    entities.add(self.sanity_bar)
    self.sanity_bar.visible = False

  def die(self):
    print "you die!!!!!!!!!!!!!!"

  def hurt(self, amt):
    if self.is_flashing(): return

    self.hp -= amt
    if self.hp <= 0:
      self.hp = 0
      self.die()

    self.hp_bar.set_amt(self.hp)
    self.hp_bar.jiggle()

    self.flash()

  def extra_max_health(self, amt):
    self.hp += amt
    self.max_hp += amt
    self.hp_bar.width += amt * 2

  def heal(self, amt):
    self.hp += amt
    if self.hp > self.max_hp:
      self.hp = self.max_hp

    self.hp_bar.set_amt(self.hp)

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

  def shoot_bullet(self, entities):
    b = Bullet(self, self.direction, 1)
    entities.add(b)

  def check_for_push(self, entities):
    pushblock = entities.get("pushable", lambda x: x.touches_rect(self))
    if len(pushblock) == 0: return

    pushblock[0].push(self.direction, entities)

  def update(self, entities):
    super(Character, self).update(entities)

    dx, dy = (0, 0)

    if UpKeys.key_down(pygame.K_x) and Tick.get(self.cooldown): self.shoot_bullet(entities)
    if UpKeys.key_down(pygame.K_LEFT):
      dx -= self.speed
      self.direction = (-1, 0)
    if UpKeys.key_down(pygame.K_RIGHT):
      dx += self.speed
      self.direction = (1, 0)
    if UpKeys.key_down(pygame.K_UP):
      self.direction = (0, -1)
    if UpKeys.key_down(pygame.K_SPACE): dy = -20

    self.vy -= GRAVITY
    dy -= self.vy
    dy = min(dy, 5)

    delta = .1
    dest_x = self.x + dx
    dest_y = self.y + dy

    self.x += dx
    self.check_for_push(entities)
    while self.collides_with_wall(entities):
      self.x -= sign(dx) or -1

    self.y += dy
    while self.collides_with_wall(entities):
      self.y -= sign(dy) or -1

    self.onground = False

    for p in zip(range(self.x + 2, self.x + self.size - 2), [self.y + self.size + 1] * self.size):
      if entities.any("wall", lambda x: x.touches_point(p)):
        self.onground = True
        break

    if self.onground:
      dy = 0
      self.vy = 0

    self.check_new_map(entities)
    self.check_sanity(entities.one("map"))

  def soft_death(self):
    print "soft death!"

  def depth(self):
    return CHAR_DEPTH

  def check_sanity(self, m):
    if self.sanity < 0: self.sanity = 0
    if self.sanity > self.max_sanity: self.sanity = self.max_sanity

    self.sanity_bar.set_amt(self.sanity)

    if self.sanity < self.max_sanity:
      self.sanity_bar.visible = True
    else:
      self.sanity_bar.visible = False

    if not m.get_lighting_rel(int(self.x/20), int(self.y/20)) > INSANE_LIGHT: 
      if self.sanity < self.max_sanity:
        if Tick.get(6): 
          self.sanity += 1
          self.sanity_bar.jiggling = 0
      return

    if Tick.get(20): 
      self.sanity -= 1
      self.sanity_bar.jiggling = 20

    if self.sanity <= 0:
      self.soft_death()

def render_all(manager):
  ch = manager.one("character")
  x_ofs = max(min(ch.x, 400 - CHAR_XY), CHAR_XY)
  y_ofs = max(min(ch.y, 400 - CHAR_XY), CHAR_XY)

  for e in sorted(manager.get("renderable"), key=lambda x: x.depth()):
    if "relative" in e.groups:
      e.render(screen, CHAR_XY-x_ofs, CHAR_XY-y_ofs)
    else:
      e.render(screen, 0, 0)

def main():
  manager = Entities()
  c = Character(40, 40, manager)
  manager.add(c)
  t = Text(c, "This is a realllllllly long text!!!!!!")
  manager.add(t)

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
    Tick.inc()

    for event in pygame.event.get():
      UpKeys.flush()
      if event.type == pygame.QUIT:
        pygame.quit()
        sys.exit()
      if event.type == pygame.KEYDOWN:
        UpKeys.add_key(event.key)
      if event.type == pygame.KEYUP:
        UpKeys.release_key(event.key)

    if UpKeys.key_down(pygame.K_w) and UpKeys.key_down(310): # Q and CMD
      break

    #TODO: Better is a updateDepth() on each entity.
    for e in sorted(manager.get("updateable"), key=lambda x: x.depth()):
      e.update(manager)

    screen.fill((255, 255, 255))

    render_all(manager)

    pygame.display.flip()


main()
