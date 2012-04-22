from __future__ import division
import sys, pygame, spritesheet, wordwrap
import random
import numpy
import math
import cProfile
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

ZOOM_SPEED = 20

MIN_LIGHT = 180
CAM_LAG = 20

CROSSFADE_SPEED = 0.03

#gameplay

MAX_HEALTH_INC = 3
INSANE_LIGHT = 150
BEAM_START_LENGTH = 5
ITEM_DRIFT_SPEED = 20

#depths

LIGHT_DEPTH = 2
SWITCH_DEPTH = 2
PUSH_BLOCK_DEPTH = 3
LIGHT_SOURCE_DEPTH = 5
ENEMY_DEPTH = 8
PARTICLE_DEPTH = 10
BULLET_DEPTH = 50
CHAR_DEPTH = 80
TEXT_DEPTH = 100
BAR_DEPTH = 200

#hax

cam_lag_override = 0
going_insane = False

DEBUG = False

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
     [[new_sheet.image_at((x, y, TILE_SIZE, TILE_SIZE), colorkey=(254,254,254))\
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
      self.img = TileSheet.get(src_file, src_x, src_y).copy()
      self.rect = self.img.get_rect()

    self.uid = get_uid()
    self.events = {}
    self.groups = groups
    self.visible = property(self.getvis, self.setvis)

    self.jiggling = 0
    self.old_xy = ()
    self.flashing = 0
    self.zooming = False
    self.zoom_pos = (0, 0)

    self.fade_out = False
    self.fade_in = False
    self.alpha = 255
    self.anim = []

  def animate(self, frames):
    self.anim = frames

  def push(self, direction, entities):
    assert "pushable" in self.groups
    direction = (direction[0], 0)

    new_x = self.x + direction[0] * TILE_SIZE
    new_y = self.y + direction[1] * TILE_SIZE

    if entities.any("wall", lambda e: e.x == new_x and e.y == new_y): return
    self.move(new_x, new_y, entities)

  def move(self, x, y, entities):
    self.x = x
    self.y = y

    if "beamlight" in self.groups: self.beamtick = BEAM_START_LENGTH

    if "persistent" not in self.groups: return

    went_offscreen = False

    if self.x < 0: 
      self.x = MAP_SIZE_PIXELS - TILE_SIZE * 2
      self.restore_map_xy = (self.restore_map_xy[0] - 1, self.restore_map_xy[1])
      went_offscreen = True
    elif self.x > MAP_SIZE_PIXELS:
      self.x = TILE_SIZE * 2
      self.restore_map_xy = (self.restore_map_xy[0] + 1, self.restore_map_xy[1])
      went_offscreen = True
    elif self.y > MAP_SIZE_PIXELS:
      self.y = TILE_SIZE * 2
      self.restore_map_xy = (self.restore_map_xy[0] + 1, self.restore_map_xy[1])
      went_offscreen = True

    if went_offscreen: self.restore_xy = (self.x, self.y)

  def getvis(self): 
    return self.visible

  def setvis(self, val): 
    if not self.visible and val: self.alpha = 255
    self.visible = val

  def zoom(self, position):
    self.zooming = True
    self.zoom_pos = position

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

  def fadein(self):
    self.alpha = 0
    self.fade_in = True

  def fadeout(self):
    if self.visible and self.alpha == 255:
      self.alpha = 255
      self.fade_out = True

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
    assert(not self.fade_out or not self.fade_in)

    if "switch" in self.groups:
      activated = False

      for e in entities.get("switchpusher"):
        if e.touches_rect(self):
          self.activate(entities)
          activated = True

          #save position of the block that's pushing the switch.
          if "persistent" in e.groups:
            e.restore_xy = (e.x, e.y)

      if not activated:
        self.deactivate(entities)

    if len(self.anim) > 0 and Tick.get(8):
      self.img = TileSheet.get("tiles.png", *self.anim.pop(0))

    if self.zooming:
      if abs(self.x - self.zoom_pos[0]) + abs(self.y - self.zoom_pos[1]) > 5:
        self.alpha = 100
        self.x += (self.zoom_pos[0] - self.x) / ZOOM_SPEED
        self.y += (self.zoom_pos[1] - self.y) / ZOOM_SPEED

        return False
      else:
        self.x = self.zoom_pos[0]
        self.y = self.zoom_pos[1]

        self.alpha = 255
        self.zooming = False

    if self.fade_out and self.alpha > 0:
      self.alpha -= 5

    if self.fade_in and self.alpha > 0:
      self.alpha += 5

    if self.jiggling > 0:
      self.x = self.x + random.randrange(-JIGG_RANGE, JIGG_RANGE)
      self.y = self.y + random.randrange(-JIGG_RANGE, JIGG_RANGE)
      self.jiggling -= 1

    if self.flashing > 0:
      #TODO: Add flashing stuff here.

      self.flashing -= 1

    return True

class Particles(Entity):
  def __init__(self):
    super(Particles, self).__init__(0, 0, ["renderable", "updateable", "relative", "particles"])

  def reinitialize(self, entities, particle_sources):
    self.surf = pygame.Surface((MAP_SIZE_PIXELS, MAP_SIZE_PIXELS), pygame.SRCALPHA) #TODO: make actual map size.
    self.particles = []
    self.beams = []
    self.particle_sources = particle_sources
    self.tick = 0

  def update(self, entities):
    return

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
    if intensity > MIN_LIGHT: intensity = MIN_LIGHT

    self.x = x
    self.y = y

    self.s = pygame.Surface((TILE_SIZE,TILE_SIZE), pygame.SRCALPHA)  # the size of your rect
    self.s.fill((0, 0, 0, intensity))

  def render(self, screen):
    screen.blit(self.s, (self.x, self.y))

# ALL the light in the game. ALL OF IT. Make it blurry, yo. Beacon it up in here. LOL BEACON? I DONT KNOW WHAT BEACON IS. ISNT THAT A CRISPY BREAKFAST FOOD? IVE NEVER HEARD OF IT LOL.
class Light(Entity):
  def __init__(self):
    super(Light, self).__init__(0, 0, ["renderable", "relative", "all-lights"])

  def reinitialize(self, light_objs, entities, m):
    self.light_objs = light_objs
    self.recalculate_light(entities, m)

  def depth(self):
    return LIGHT_DEPTH

  def get_lighting_rel(self, x, y):
    return self.ambient_light[x][y]

  def calculate_ambient_light(self, entities, m):
    ambient_light = [[255 for x in range(MAP_SIZE_TILES)] for y in range(MAP_SIZE_TILES)]

    for source in entities.get("light-source"):
      light_deltas = source.calculate_light_deltas(entities, m)
      for i, elem in enumerate(light_deltas):
        for j, delta in enumerate(elem):
          ambient_light[i][j] += delta

          if ambient_light[i][j] > 255: ambient_light[i][j] = 255
          if ambient_light[i][j] < 0: ambient_light[i][j] = 0

    self.ambient_light = ambient_light

  def recalculate_light(self, entities, m):
    self.surf = pygame.Surface((MAP_SIZE_PIXELS, MAP_SIZE_PIXELS), pygame.SRCALPHA)

    self.calculate_ambient_light(entities, m)

    # calculate ambient light of each (x,y) position.
    self.spots = [[None for x in range(MAP_SIZE_TILES)] for y in range(MAP_SIZE_TILES)]
    for x in range(MAP_SIZE_TILES):
      for y in range(MAP_SIZE_TILES):
        self.spots[x][y] = LightSpot(x * TILE_SIZE, y * TILE_SIZE, self.ambient_light[x][y])

    # build an array of every beam object created by every light.
    self.beams = []

    for source in self.light_objs:
      if "beamlight" in source.groups:
        for beam_pos in source.light_beam_pos():
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
    self.anim = []
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

# weighted random choice
# takes [(item, weight), (item2, weight)], gives item.
def w_choice(lst):
  n = random.uniform(0, 1)
  for item, weight in lst:
    if n < weight:
      break
    n = n - weight
  return item


class Map(Entity):
  def __init__(self):
    self.full_map_size = MAP_SIZE_TILES
    self.mapx = 0
    self.mapy = 0
    self.visible_map_size = VISIBLE_MAP_SIZE
    self.light_deltas = None
    self.seen_maps = []

    super(Map, self).__init__(0, 0, ["updateable", "map"])

  def get_mapxy(self):
    return (self.mapx, self.mapy)

  def update(self, entities):
    super(Map, self).update(entities)

  def new_map_rel(self, entities, dx, dy):
    self.new_map_abs(entities, self.mapx + dx, self.mapy + dy)

  def in_bounds(self, point):
    return point[0] >= 0 and point[1] >= 0 and point[0] < MAP_SIZE_PIXELS and point[1] < MAP_SIZE_PIXELS

  def new_map_abs(self, entities, x, y):
    self.mapx = x
    self.mapy = y
    new_map = (self.mapx, self.mapy) not in self.seen_maps
    self.seen_maps.append((self.mapx, self.mapy))

    entities.remove_all("map_element")

    self.mapdata = TileSheet.get('laderp.bmp', self.mapx, self.mapy)

    mapping = { (0, 0, 0): 1 # Background
              , (255, 255, 255): 0 # Wall
              , (255, 0, 0): 2 #dumbEnemy
              , (0, 0, 100): 3 # beam light source
              , (100, 100, 100): 4 #reflector
              , (0, 0, 255): 5 # radial light source
              , (200, 0, 0): 6 # sentry
              , (50, 0, 0): 7 # science-wall
              , (100, 0, 0): 8 # sweeper
              , (222, 222, 222): 9 # push-crate
              , (0, 255, 0): 10 # switch
              , (0, 100, 0): 11 # lock-box
              }

    self.tiles = [[None for i in range(MAP_SIZE_TILES)] for j in range(MAP_SIZE_TILES)]

    particle_sources = []
    light_sources = []

    all_colors = [[mapping[tupleize(self.mapdata.get_at((i, j)))] for j in range(MAP_SIZE_TILES)] for i in range(MAP_SIZE_TILES)]

    for i in range(MAP_SIZE_TILES):
      for j in range(MAP_SIZE_TILES):
        colors = all_colors[i][j]

        if colors == 0:
          backgrounds = [((0, 0), 0.9), ((10, 0), 0.03), ((11, 0), 0.03), ((12, 0), 0.04)]
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, *w_choice(backgrounds))
        elif colors == 1: # dirt 'wall'
          backgrounds = []
          if j > 0 and all_colors[i][j - 1] == 1: # if dirt above current position
            backgrounds = [((5, 1), 1.0)]
          else:
            backgrounds = [((2, 0), 0.8), ((1, 0), 0.1), ((4, 1), 0.1)]
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, *w_choice(backgrounds))
          tile.add_group("wall")
        elif colors == 2:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          entities.add(Enemy(i * TILE_SIZE, j * TILE_SIZE, Enemy.STRATEGY_STUPID))
        elif colors == 3:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          particle_sources.append([i * TILE_SIZE, j * TILE_SIZE])
          if new_map: light_sources.append([i * TILE_SIZE, j * TILE_SIZE, LightSource.BEAM])
        elif colors == 4:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          entities.add(Reflector(i * TILE_SIZE, j * TILE_SIZE, None))
        elif colors == 5:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          #particle_sources.append([i * TILE_SIZE, j * TILE_SIZE])
          if new_map: light_sources.append([i * TILE_SIZE, j * TILE_SIZE, LightSource.RADIAL])
        elif colors == 6:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          entities.add(Enemy(i * TILE_SIZE, j * TILE_SIZE, Enemy.STRATEGY_SENTRY))
        elif colors == 7:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 16, 0)
          tile.add_group("wall")
        elif colors == 8:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          entities.add(Enemy(i * TILE_SIZE, j * TILE_SIZE, Enemy.STRATEGY_SWEEPER))
        elif colors == 9:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          if new_map: entities.add(PushBlock(i * TILE_SIZE, j * TILE_SIZE, self))
        elif colors == 10:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 0, 0)
          entities.add(Switch(i * TILE_SIZE, j * TILE_SIZE, self))
        elif colors == 11:
          tile = Tile(i * TILE_SIZE, j * TILE_SIZE, 7, 2)
          tile.add_group("lock")
          tile.add_group("wall")

        tile.add_group("map_element")
        entities.add(tile)
        self.tiles[i][j] = tile

    for e in entities.get("persistent"):
      e.x = e.restore_xy[0]
      e.y = e.restore_xy[1]

    self.calculate_lighting(light_sources, entities)

  def is_wall_rel(self, i, j):
    if i < 0 or j < 0 or i >= MAP_SIZE_TILES or j >= MAP_SIZE_TILES: return True
    return "wall" in self.tiles[i][j].groups

  def calculate_lighting(self, light_sources, entities):
    # everything starts dark.
    light_objs = []

    # Sources need to be aware of the entire map, so we add them last.
    for source in light_sources:
      new_l = LightSource(source[0], source[1], entities, self, source[2])
      light_objs.append(new_l)
      entities.add(new_l)

    # the only things that generate particles currently are lights. thats why i pass in light_objs, not particle_objs.
    entities.one("particles").reinitialize(entities, light_objs)
    entities.one("all-lights").reinitialize(light_objs, entities, self)

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
  def __init__(self, follow, color_health, color_no_health, amt, max_amt, y_ofs=0):
    super(Bar, self).__init__(follow.x, follow.y, ["renderable", "updateable", "healthbar", "relative"])
    self.amt = amt
    self.max_amt = max_amt
    self.color_health = color_health
    self.color_no_health = color_no_health
    self.follow = follow

    self.width = 40
    self.height = 8
    self.border_width = 2
    self.y_ofs = y_ofs

    self.img = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
  def set_amt(self, x):
    self.amt = x

  def set_max_amt(self, x):
    self.max_amt = x

  def depth(self):
    return BAR_DEPTH

  def update(self, entities):
    self.x = self.follow.x - self.follow.size / 2
    self.y = self.follow.y - 10 - self.y_ofs

    # Outer border
    pygame.draw.rect(self.img, (0, 0, 0), (0, 0, self.width, self.height))

    # Inside
    actual_w = self.width - self.border_width * 2
    actual_h = self.height - self.border_width * 2
    pygame.draw.rect(self.img, self.color_no_health, (self.border_width, self.border_width, actual_w, actual_h))

    # 'Health'
    health_w = (self.amt / self.max_amt) * actual_w
    pygame.draw.rect(self.img, self.color_health, (self.border_width, self.border_width, health_w, actual_h))

    super(Bar, self).update(entities)

  def render(self, screen, dx, dy):
    if not self.visible: return
    if self.alpha <= 0:
      self.visible = False

    #self.img.set_alpha(self.alpha) #TODO WHAT IN GODS NAME?

    screen.blit(self.img, (self.x + dx, self.y + dy))

class PushBlock(Entity):
  def __init__(self, x, y, m):
    self.direction = [1, 0]
    super(PushBlock, self).__init__(x, y, ["renderable", "updateable", "switchpusher", "persistent", "wall", "pushable", "relative"], 6, 2, "tiles.png")
    self.restore_xy = (self.x, self.y)
    self.restore_map_xy = m.get_mapxy()

  def depth(self):
    return PUSH_BLOCK_DEPTH

  def update(self, entities):
    if not entities.one("map").get_mapxy() == self.restore_map_xy: 
      self.visible = False
      return

    self.visible = True

    super(PushBlock, self).update(entities)

class Switch(Entity):
  def __init__(self, x, y, m):
    super(Switch, self).__init__(x, y, ["renderable", "updateable", "switch", "relative"], 4, 3, "tiles.png")
    self.restore_map_xy = m.get_mapxy()

  def depth(self):
    return SWITCH_DEPTH

  def update(self, entities):
    if not entities.one("map").get_mapxy() == self.restore_map_xy: 
      self.visible = False
      return

    self.visible = True

    super(Switch, self).update(entities)

  def activate(self, entities):
    for e in entities.get("lock"):
      if "wall" in e.groups:
        e.groups.remove("wall")
        e.animate([[0, 0]])
        self.animate([[5, 3]])

  def deactivate(self, entities):
    for e in entities.get("lock"):
      if "wall" not in e.groups:
        print "adding wall to ", e.uid
        e.add_group("wall")
        e.animate([[7, 2]])
        self.animate([[4, 3]])

class Reflector(Entity):
  def __init__(self, x, y, type):
    self.direction = [1, 0]
    super(Reflector, self).__init__(x, y, ["renderable", "reflector", "relative"], 6, 0, "tiles.png")

  def reflect(self, direction):
    return [direction[1], -direction[0]]

class Pickup(Entity):
  HEALTH = 0

  def __init__(self, x, y, type):
    if type == Pickup.HEALTH:
      super(Pickup, self).__init__(x, y, ["renderable", "pickupable", "updateable", "relative"], 13, 0, "tiles.png")
    else:
      assert(False)

  def pickup(self, ch):
    ch.heal(3)

class Enemy(Entity):
  STRATEGY_STUPID = 0
  STRATEGY_SENTRY = 1
  STRATEGY_SWEEPER = 2

  hp = {STRATEGY_STUPID: 5, STRATEGY_SENTRY: 4, STRATEGY_SWEEPER: 6}

  def __init__(self, x, y, type):
    self.speed = 3
    self.type = type
    self.hp = Enemy.hp[self.type]
    self.ticker = 0

    self.direction = [1, 0]
    if self.type == Enemy.STRATEGY_STUPID:
      super(Enemy, self).__init__(x, y, ["renderable", "updateable", "knocked", "enemy", "relative", "map_element"], 4, 0, "tiles.png")
    elif self.type == Enemy.STRATEGY_SENTRY:
      super(Enemy, self).__init__(x, y, ["renderable", "updateable", "enemy", "relative", "map_element"], 7, 1, "tiles.png")
    elif self.type == Enemy.STRATEGY_SWEEPER:
      super(Enemy, self).__init__(x, y, ["renderable", "updateable", "knocked", "enemy", "relative", "map_element"], 9, 1, "tiles.png")


  def update(self, entities):
    super(Enemy, self).update(entities)
    ch = entities.one("character")

    if self.type == Enemy.STRATEGY_STUPID:
      self.be_stupid(entities)
    elif self.type == Enemy.STRATEGY_SENTRY:
      self.be_sentry(entities, ch)
    elif self.type == Enemy.STRATEGY_SWEEPER:
      self.be_sweeper(entities, ch)

    if self.touches_rect(ch):
      ch.hurt(1)

  def depth(self):
    return ENEMY_DEPTH

  def die(self, entities):
    entities.remove(self)

    entities.add(Pickup(self.x, self.y, Pickup.HEALTH))

  def hurt(self, amt, entities, dir):
    self.hp -= 1
    if self.hp <= 0:
      self.die(entities)
    else:
      if "knocked" in self.groups:
        self.knockback(5, entities, (sign(dir[0]), sign(dir[1])))

  def knockback(self, dist, entities, dir):
    while not self.collides_with_wall(entities) and dist > 0:
      dist -= 1
      self.x += dir[0]
      self.y += dir[1]

    self.x -= dir[0]
    self.y -= dir[1]

  def be_sweeper(self, entities, ch):
    if ch.y != self.y: 
      self.img = TileSheet.get("tiles.png", 9, 1)
      return

    self.img = TileSheet.get("tiles.png", 9, 0)
    m = entities.one("map")

    amount = 6
    dx = sign(ch.x - self.x)
    while not self.collides_with_wall(entities) and amount > 0:
      self.x += dx
      amount -= 1
    self.x -= dx

  def be_sentry(self, entities, ch):
    if Tick.get(20):
      self.ticker += 1
      self.img = TileSheet.get("tiles.png", 7 + self.ticker % 2, 1)

    if Tick.get(20):
      spd = 1
      mag = math.sqrt((self.x - ch.x) ** 2 + (self.y - ch.y) ** 2)
      direct = (spd * (ch.x - self.x) / mag, spd * (ch.y - self.y) / mag)
      b = Bullet(self, direct, 1)
      entities.add(b)
  
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

    if light_type == LightSource.BEAM:
      super(LightSource, self).__init__(x, y, ["wall", "pushable", "renderable", "relative", "updateable", "persistent", "light-source"], 5, 0, "tiles.png")
    elif light_type == LightSource.RADIAL:
      super(LightSource, self).__init__(x, y, ["wall", "pushable", "renderable", "relative", "updateable", "persistent", "light-source"], 4, 2, "tiles.png")

    self.restore_xy = (self.x, self.y)
    self.restore_map_xy = m.get_mapxy()

    if light_type == LightSource.BEAM:
      self.beamtick = BEAM_START_LENGTH
      self.groups.append("beamlight")

    assert(self.x % TILE_SIZE == 0)
    assert(self.y % TILE_SIZE == 0)

  def calculate_light_deltas(self, entities, m):
    if self.light_type == LightSource.BEAM:
      self.beamtick += 1
      return self.beam_deltas(entities, m)
    elif self.light_type == LightSource.RADIAL:
      return self.radial_deltas(entities, m)

  def radial_deltas(self, entities, m):
    radius = 500
    pts = []
    deltas = [[0 for x in range(MAP_SIZE_TILES)] for y in range(MAP_SIZE_TILES)]

    if not self.visible: return deltas

    for x in range(self.x - radius, self.x + radius + 1, TILE_SIZE):
      for y in range(self.y - radius, self.y + radius + 1, TILE_SIZE):
        if x == self.x - radius or x == self.x + radius or y == self.y - radius or y == self.y + radius:
          pts.append((x, y))

    for x, y in pts:
      pt = [self.x, self.y]

      #raycast to (x, y) and light up everything along the way.
      dx = (x - self.x) * TILE_SIZE / radius
      dy = (y - self.y) * TILE_SIZE / radius

      for i in range(radius):
        if not m.in_bounds((pt[0], pt[1])): break
        if m.is_wall_rel(int(pt[0] / 20), int(pt[1] / 20)): break
        deltas[int(pt[0] / 20)][int(pt[1] / 20)] = self.intensity #* (1 - (i + 20) / (radius + 20))
        pt[0] = pt[0] + dx
        pt[1] = pt[1] + dy

    return deltas

  def update(self, entities):
    m = entities.one("map")

    if not m.get_mapxy() == self.restore_map_xy: 
      self.visible = False
      return

    self.visible = True

    if not m.is_wall_rel(int(self.x / TILE_SIZE), int(self.y / TILE_SIZE) + 1) and Tick.get(8):
      self.move(self.x, self.y + TILE_SIZE, entities)

  def light_beam_pos(self):
    return self.lightbeampos

  def beam_deltas(self, entities, m):
    self.lightbeampos = []
    deltas = [[0 for x in range(MAP_SIZE_TILES)] for y in range(MAP_SIZE_TILES)]

    if not self.visible: return deltas

    pos_abs = [self.x, self.y]
    pos_rel = [int(self.x / TILE_SIZE), int(self.y / TILE_SIZE)]
    cur_dir = self.direction

    length = 0
    while m.in_bounds(pos_abs) and not entities.any("wall", lambda e: e.x == pos_abs[0] and e.y == pos_abs[1] and e.uid != self.uid):
      length += 1
      if length > self.beamtick: break
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
    self.dying = False

    self.char_is_owner = "character" in owner.groups

    if "character" in owner.groups:
      if direction[1] == 0:
        super(Bullet, self).__init__(owner.x, owner.y + random.randrange(-4, 4), ["renderable", "updateable", "bullet", "relative", "map_element"], 3, 0, "tiles.png")
      else:
        super(Bullet, self).__init__(owner.x + random.randrange(-4, 4), owner.y, ["renderable", "updateable", "bullet", "relative", "map_element"], 0, 5, "tiles.png")
    else:
      super(Bullet, self).__init__(owner.x, owner.y, ["renderable", "updateable", "bullet", "relative", "map_element"], 5, 2, "tiles.png") # why not 0, 15? i have no idea!

    self.x += int(direction[0] * owner.size / 2)
    self.y += int(direction[1] * owner.size / 2)

  def depth(self):
    return BULLET_DEPTH

  def die(self):
    self.dying = True
    self.ticks = 0

  def death_anim(self, entities):
    if Tick.get(5):
      self.ticks += 1
      if self.ticks == 3:
        entities.remove(self)
      else:
        self.img = TileSheet.get("tiles.png", 3, self.ticks)

  def update(self, entities):
    if self.dying:
      self.death_anim(entities)
      return

    super(Bullet, self).update(entities)

    self.x += self.direction[0] * self.speed
    self.y += self.direction[1] * self.speed

    if not entities.one("map").in_bounds((self.x, self.y)):
      self.die()
      return

    hitlambda = lambda x: x.touches_point((self.x + self.size/2, self.y + self.size/2))

    walls_hit = entities.get("wall", hitlambda)
    if len(walls_hit) > 0:
      self.die()
      return

    if self.char_is_owner:
      enemies_hit = entities.get("enemy", hitlambda)
      if len(enemies_hit) > 0:
        self.die()
        enemies_hit[0].hurt(self.dmg, entities, self.direction)
        return
    else:
      ch = entities.get("character", hitlambda)
      if len(ch) > 0:
        ch[0].hurt(1)
        self.die()
        return

class Character(Entity):
  def __init__(self, x, y, entities):
    super(Character, self).__init__(x, y, ["renderable", "switchpusher", "updateable", "character", "relative"], 0, 1, "tiles.png")
    self.animticker = 0

    self.speed = 5
    self.vy = 0
    self.onground = False
    self.cooldown = 5
    self.direction = (1, 0)
    self.last_safe_place = (x, y)

    self.hp = 5
    self.max_hp = 5

    self.hp_bar = Bar(self, (0, 255, 0), (255, 0, 0), self.hp, self.max_hp, 20)
    entities.add(self.hp_bar)
    self.hp_bar.visible = False

    self.sanity = 10
    self.max_sanity = 10

    self.sanity_bar = Bar(self, (255, 255, 255), (0, 0, 0), self.sanity, self.max_sanity)
    entities.add(self.sanity_bar)
    self.sanity_bar.visible = False

  def die(self):
    print "you die!!!!!!!!!!!!!!"
    assert(False)

  def hurt(self, amt):
    if self.is_flashing(): return

    self.hp -= amt
    if self.hp <= 0:
      self.hp = 0
      self.die()

    self.hp_bar.set_amt(self.hp)
    self.hp_bar.jiggle()
    self.hp_bar.visible = True
    self.hp_bar.alpha = 255
    self.hp_bar.fadeout()

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
    self.hp_bar.visible = True
    self.hp_bar.alpha = 255
    self.hp_bar.fadeout()

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

      # Force instant camera update.
      global cam_lag_override
      cam_lag_override = 1

  def shoot_bullet(self, entities):
    b = Bullet(self, self.direction, 1)
    entities.add(b)

  def check_for_push(self, entities):
    pushblock = entities.get("pushable", lambda x: x.touches_rect(self))
    if len(pushblock) == 0: return

    pushblock[0].push(self.direction, entities)

  def take_pickups(self, entities):
    for item in entities.get("pickupable"):
      if item.touches_rect(self):
        item.pickup(self)
        entities.remove(item)
      else:
        item.x += (self.x - item.x) / ITEM_DRIFT_SPEED
        item.y += (self.y - item.y) / ITEM_DRIFT_SPEED

  def update(self, entities):
    self.x = int(self.x)
    self.y = int(self.y)

    can_update = super(Character, self).update(entities)

    self.take_pickups(entities)

    if not can_update: return

    dx, dy = (0, 0)

    if UpKeys.key_down(pygame.K_x) and Tick.get(self.cooldown): self.shoot_bullet(entities)
    if UpKeys.key_down(pygame.K_LEFT):
      dx -= self.speed
      self.direction = (-1, 0)
      if Tick.get(8): self.animticker = (self.animticker + 1) % 4
      self.img = TileSheet.get("tiles.png", self.animticker, 4)
    if UpKeys.key_down(pygame.K_RIGHT):
      dx += self.speed
      self.direction = (1, 0)
      if Tick.get(8): self.animticker = (self.animticker + 1) % 4
      self.img = TileSheet.get("tiles.png", self.animticker, 3)

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
    self.check_sanity(entities)

  def soft_death(self):
    self.fadein()
    self.zoom(self.last_safe_place)

  def depth(self):
    return CHAR_DEPTH

  def check_sanity(self, entities):
    if self.sanity < 0: self.sanity = 0
    if self.sanity > self.max_sanity: self.sanity = self.max_sanity

    self.sanity_bar.set_amt(self.sanity)

    if self.sanity < self.max_sanity:
      self.sanity_bar.visible = True
    else:
      self.sanity_bar.fadeout()

    # We're in a reasonable amount of light.
    if not entities.one("all-lights").get_lighting_rel(int(self.x/20), int(self.y/20)) > INSANE_LIGHT: 
      global going_insane
      going_insane = False

      self.last_safe_place = (self.x, self.y)

      if self.sanity < self.max_sanity:
        if Tick.get(6): 
          self.sanity += 1
          self.sanity_bar.jiggling = 0
      return

    global going_insane
    going_insane = True

    if Tick.get(20): 
      self.sanity -= 1
      self.sanity_bar.jiggling = 20

    if self.sanity <= 0:
      self.soft_death()

def render_all(manager, lag = CAM_LAG):
  global cam_lag_override
  if cam_lag_override != 0:
    lag = cam_lag_override
    cam_lag_override = 0

  ch = manager.one("character")
  x_ofs_actual = max(min(ch.x, 400 - CHAR_XY), CHAR_XY)
  y_ofs_actual = max(min(ch.y, 400 - CHAR_XY), CHAR_XY)

  x_ofs = render_all.old_xofs + (x_ofs_actual - render_all.old_xofs) / lag
  y_ofs = render_all.old_yofs + (y_ofs_actual - render_all.old_yofs) / lag

  render_all.old_xofs = x_ofs
  render_all.old_yofs = y_ofs

  for e in sorted(manager.get("renderable"), key=lambda x: x.depth()):
    if "relative" in e.groups:
      e.render(screen, CHAR_XY-x_ofs, CHAR_XY-y_ofs)
    else:
      e.render(screen, 0, 0)

render_all.old_xofs = 40
render_all.old_yofs = 40

def main():
  manager = Entities()
  c = Character(40, 40, manager)
  manager.add(c)
  t = Text(c, "This is a realllllllly long text!!!!!!")
  manager.add(t)

  manager.add(Light())
  manager.add(Particles())

  m = Map()
  m.new_map_abs(manager, 0, 0)
  manager.add(m)

  pygame.display.init()
  pygame.font.init()

  normal_sound = None
  dark_sound = None

  if not DEBUG:
    pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)

    normal_sound = pygame.mixer.Sound('soundtrack-normal.ogg')
    dark_sound   = pygame.mixer.Sound('soundtrack-dark.ogg')

    normal_sound.play(-1)

    dark_sound.play(-1)
    dark_sound.set_volume(0.0)

  while True:
    if going_insane:
      if normal_sound.get_volume() > 0.1:
        normal_sound.set_volume(normal_sound.get_volume() - CROSSFADE_SPEED)
        dark_sound.set_volume(1 - normal_sound.get_volume())
    else:
      if dark_sound.get_volume() > 0.1:
        normal_sound.set_volume(normal_sound.get_volume() + CROSSFADE_SPEED)
        dark_sound.set_volume(1 - normal_sound.get_volume())

    print normal_sound.get_volume()

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

    if Tick.get(5):
      manager.one("all-lights").recalculate_light(manager, manager.one("map"))

    screen.fill((0, 0, 0))

    render_all(manager)

    pygame.display.flip()

#cProfile.run('main()')
main()
