"""A continuous card spring, ace turnover, pressure fan and four-packet cut.

Coordinates use one card height as their unit. Cards in a held packet share its bend and orientation.
Children of the last grip move in its local coordinates, so a tilted fan can
stay together even when its individual cards overlap in the camera projection.
"""
from dataclasses import dataclass
import math

import numpy as np

from card_geometry import CARD_WIDTH, STOCK, rotation
from pack_order import FACES

CUT_PERIOD = 13.6
SPRING_START = 6.8
SPRING_TIME = 3.8
LOAD_TIME = .50
UNLOAD_TIME = .44
GRIP_BOW = .33
GRIP_DRAW = np.array((-.095, -.025, .055))
ACE_LEAVE = 2.72
# Fractions of the detached ace's flight, with room to take off and land face-up.
ACE_FLIP_START = .12
ACE_FLIP_DURATION = .82
ACE_BACK_TIME = SPRING_START + ACE_LEAVE + (ACE_FLIP_START + .5*ACE_FLIP_DURATION)*(SPRING_TIME - ACE_LEAVE)
CATCH_TIME = .27
PIVOT_START = 7.10
PIVOT_END = 8.59
PERIOD = CUT_PERIOD + SPRING_TIME
PAPER_GAP = .00024
PITCH = STOCK + PAPER_GAP
LIFT = .73
SOURCE = np.array((-1.03,-.14,LIFT))
CATCH = np.array((1.04,.22,0.))
COUNTS = (16,14,12,6,1,1,1,1)
OPENING = 5.46

def playback_time(seconds):
    return (seconds+OPENING) % PERIOD

def stock_depth(count):
    return STOCK + (count-1)*PITCH
TAU = 2 * math.pi
CLEARANCE = .009
TOP_COUNTS = (6, 1, 1, 1, 1)
TOP_FACES = tuple(FACES[i] for i in (47,48,49,50,51))
FAN_PIN = np.array((.07, .43, 0.))
FAN_HUB = np.array((.15, .36, 0.))
FAN_START, FAN_PEAK, FAN_END = .655, .862, .995
FAN_FIRST_ANGLE = -93.
FAN_STEP = 19.
FAN_PALM = FAN_HUB - rotation((0., 0., FAN_FIRST_ANGLE)) @ FAN_PIN


@dataclass(frozen=True)
class Body:
    center: np.ndarray
    rotation: np.ndarray
    face: str
    count: int
    bend: float = 0.

    @property
    def thickness(self):
        return stock_depth(self.count)


def smooth(x):
    u = min(1., max(0., x))
    return u**3 * (10 + u * (-15 + 6*u))


def beat(t, start, peak, end):
    return smooth((t-start)/(peak-start)) * (1-smooth((t-peak)/(end-peak)))


def fan_pressure(fan, leaf, closing):
    # The thumb reaches successive edges as it opens and sweeps back to close.
    order = leaf / 9 if closing else 1 - leaf / 9
    return fan * (1 - .62 * order * (1-fan))


def depth_extent(basis, count, loose=1., bend=0.):
    half = (CARD_WIDTH/2, .5, stock_depth(count)/2)
    return float(np.sqrt(basis[2]**2 + (.003*loose)**2) @ half) + abs(basis[2,2]*bend)*.67


def envelope(values, upper, loose):
    # Smooth over-estimates of the upper and lower convex support.
    sign = 1 if upper else -1
    if loose<1e-9:
        return max(values) if upper else min(values)
    scale=.006*loose
    return sign * scale * np.logaddexp.reduce(np.asarray(values) * (sign/scale))


def score(t):
    p = t % CUT_PERIOD / CUT_PERIOD
    angle = TAU*p
    cut = beat(p,.065,.305,.523)
    ribbon = beat(p,.398,.553,.736)
    fan = beat(p,FAN_START,FAN_PEAK,FAN_END)
    flip = smooth((p-.585)/.189)
    return p,angle,cut,ribbon,fan,flip


def crown(t, loose):
    """The ten top cards share one reference frame but can fan out or turn."""
    p,a,cut,ribbon,fan,flip = score(t)
    ceiling = 0.
    cards = []
    for index, (count, face) in enumerate(zip(TOP_COUNTS,TOP_FACES)):
        u = index/(len(TOP_COUNTS)-1)
        spread = (1-.94*cut)*(1-.47*ribbon)
        yaw = (-35 + 59*u + 13*math.sin(a-.3)*u)*spread
        yaw += 9*cut
        roll = 1.7*math.cos(a-u*.7) - (360*flip if index==4 else 0)
        pitch = 2.5*math.sin(a+u*.9)*(1-cut)
        if index==4:
            yaw += 46*math.sin(math.pi*flip)**2
        if fan > 0.:
            # The six-card grip ends at leaf five. The four loose cards carry
            # the same spacing out to the ace at the far end of the arc.
            last_leaf = 5 + index
            pressure = fan_pressure(fan, last_leaf, p > FAN_PEAK)
            target_yaw = FAN_FIRST_ANGLE + FAN_STEP * last_leaf
            yaw += (target_yaw - yaw) * pressure
            pitch *= 1 - pressure
            level_roll = -360. if index == 4 else 0.
            roll += (level_roll-roll) * pressure
        basis = rotation((pitch*loose,roll*loose,yaw*loose))
        pivot = basis @ np.array((.045,.40,0.))
        # After the catch, the ace swings around its near edge as the rest
        # of the packet opens. Its face stays visible during the handoff.
        swing_x = swing_y = pivot_lift = 0.
        if index == 4 and PIVOT_START < t < PIVOT_END:
            turn = smooth((t - PIVOT_START) / (PIVOT_END - PIVOT_START))
            twist = rotation((0., 0., -360. * turn))
            pin = np.array((-.28, .14, 0.))
            swing_x, swing_y, _ = basis @ (pin - twist @ pin)
            basis = basis @ twist
            pivot_lift = .065 * math.sin(math.pi * turn)**2
        x = (.045-pivot[0]+.10*(u-.5))*(1-ribbon)
        y = (.40-pivot[1])*(1-ribbon)
        x += .93*ribbon*(u-.42) + .052*math.sin(2*a+u)*(1-cut)
        y += .10*ribbon*math.sin(math.pi*1.5*u) + .025*math.cos(a-u)
        if fan > 0.:
            # All ten inner corners converge on one thumb position as the
            # visible rank marks spread around the outside of the fan.
            pin_offset = basis @ FAN_PIN
            x += pressure * (FAN_HUB[0] - pin_offset[0] - x)
            y += pressure * (FAN_HUB[1] - pin_offset[1] - y)
        gap = PAPER_GAP + loose*(CLEARANCE-PAPER_GAP)*(1-fan) + .0014*fan
        # The last grip releases six actual leaves into the final pressure fan.
        # Their tops are ordered along the grip normal, even at maximum spread.
        if index==0 and fan>0.:
            leaves=[]
            for j in range(count):
                opening = fan_pressure(fan, j, p > FAN_PEAK)
                twist = rotation((0, 0, (j-5)*FAN_STEP*opening))
                relative = FAN_PIN - twist @ FAN_PIN
                relative[2]=(j-(count-1)/2)*(PITCH+.0014*fan)
                leaves.append((basis@relative,basis@twist,FACES[42+j]))
            extents=[depth_extent(b,1,loose) for _,b,_ in leaves]
            lo=envelope([c[2]-e for (c,_,_),e in zip(leaves,extents)],False,fan*.15)
            hi=envelope([c[2]+e for (c,_,_),e in zip(leaves,extents)],True,fan*.15)
            z=ceiling+gap-lo
            center=np.array((x*loose,y*loose,z))
            cards.extend(Body(center+c,b,ink,1) for c,b,ink in leaves)
            ceiling=z+hi
            continue
        extent = depth_extent(basis,count,loose)
        z = ceiling + gap + extent
        if index==4:
            z += .21*loose*math.sin(math.pi*flip)**2
            x += .17*math.sin(math.pi*flip)**2
            z += pivot_lift
        ceiling = z + extent
        center = np.array((x*loose + swing_x, y*loose + swing_y, z))
        cards.append(Body(center, basis, face, count))
    return cards


def concertina(t, loose):
    p,a,cut,ribbon,fan,flip = score(t)
    identity = np.eye(3)
    groups = [
        [Body(np.zeros(3), identity, face, count)]
        for count,face in ((16,FACES[15]),(14,FACES[29]),(12,FACES[41]))
    ] + [crown(t,loose)]

    bottom = -.21
    packets = []
    for i,group in enumerate(groups):
        u = i/3.
        # Each fold opens slightly later. The blades meet at alternate long
        # edges; the camera can see between them at the widest part of the cut.
        opening = beat(p,.050+i*.020,.277+i*.018,.492+i*.012)
        pitch = (3.*math.sin(a-.38*i) + (i-1.5)*4.*ribbon)
        pitch += cut * ((16 if i%2==0 else -12) + 5*math.sin(a+u))
        hinge = (1 if i%2==0 else -1)*opening*(43 if i==3 else 49)
        yaw = (-33+36*u)*(1-cut) - 10*cut + 4.*math.sin(a+.45*i)
        yaw += cut*((u-.5)*22 + 8*math.sin(3*a+u))
        if fan > 0.:
            # The lower packets settle into the palm under the first leaf.
            # Keep the rank marks on the upper ten visible from the front.
            pitch *= 1-fan
            yaw += ((FAN_FIRST_ANGLE if i < 3 else 0.) - yaw) * fan
        basis = rotation((pitch*loose,hinge*loose,yaw*loose))
        centers = [basis @ c.center for c in group]
        axes = [basis @ c.rotation for c in group]
        supports = [depth_extent(b,c.count,loose) for b,c in zip(axes,group)]
        lows = [v[2]-e for v,e in zip(centers,supports)]
        highs = [v[2]+e for v,e in zip(centers,supports)]
        if i == 3 and fan > 0.:
            # Count the six-card grip once at the packet boundary. Switching
            # from one support to six used to lift the whole fan in one frame.
            lows = [envelope(lows[:6],False,.15*fan), *lows[6:]]
            highs = [envelope(highs[:6],True,.15*fan), *highs[6:]]
        lo = envelope(lows,False,loose)
        hi = envelope(highs,True,loose)
        z = bottom + PAPER_GAP + loose*(CLEARANCE-PAPER_GAP) - lo
        bottom = z + hi
        x = (.29*(u-.5))*(1-cut) + 1.39*(u-.56)*ribbon
        x += .085*math.sin(a+.7*i) + (-.17+.12*i)*fan
        y = (-.05+.11*math.sin(a+.62*i))*(1-.5*cut) + .12*ribbon*(u-.5)
        if fan > 0.:
            palm_x, palm_y = FAN_PALM[:2] if i < 3 else (0., 0.)
            x += (palm_x-x)*fan
            y += (palm_y-y)*fan
        shift = np.array((x*loose,y*loose,z))
        packets.extend(Body(v+shift,b,c.face,c.count) for v,b,c in zip(centers,axes,group))
    return packets, bottom



def timeline(seconds):
    t=seconds % PERIOD
    if t<SPRING_START:
        return t,smooth((t-(SPRING_START-1.66))/(1.66-LOAD_TIME)),False
    end=SPRING_START+SPRING_TIME
    if t<=end:
        return SPRING_START,1.,True
    return t-SPRING_TIME,1-smooth((t-end-CATCH_TIME)/(1.54-CATCH_TIME)),False


def spring_load(seconds):
    """Pressure builds in the grip and unwinds while the first cards leave."""
    if seconds < 0.:
        return smooth(1. + seconds / LOAD_TIME)
    return 1. - smooth(seconds / UNLOAD_TIME)


def spring(seconds):
    # Bottom cards leave first and land first. Paper identity and stock order
    # are preserved, even while both packets and the airborne trail coexist.
    flight=.58
    cadence=(3.20-flight)/51
    elapsed=seconds/SPRING_TIME
    sweep=math.sin(math.pi*elapsed)**2
    load = spring_load(seconds)
    grip_bend = -GRIP_BOW * load
    draw = GRIP_DRAW * load
    heading = rotation((0., 0., -17. + 28. * smooth(elapsed) - 9.*load))
    previous=1.
    ceiling=None
    cards=[]
    states=[]
    for index in range(52):
        delay=index*cadence + .019*math.sin(index*math.pi*4/51)
        is_ace=index==51
        if is_ace:
            delay = ACE_LEAVE
        duration=SPRING_TIME-delay if is_ace else flight
        raw=min(1.,max(0.,(seconds-delay)/duration))
        u=raw*raw*(3-2*raw)
        arch=math.sin(math.pi*raw)**2 if 0<raw<1 else 0.
        ripple=math.sin(2*math.pi*u)
        flight_bend = -.105*arch*(1-.38*u)
        bend = grip_bend + flight_bend
        basis = heading
        if is_ace and 0. < raw < 1.:
            turn = smooth((raw - ACE_FLIP_START) / ACE_FLIP_DURATION)
            basis = heading @ rotation((0., -360.*turn, -9.*math.sin(TAU*turn)))
        extent=depth_extent(basis,1,arch,flight_bend)
        if ceiling is None:
            ceiling=-.21 + LIFT*(1-u) + draw[2]
        else:
            ceiling+=LIFT*(previous-u)
        z=ceiling+PAPER_GAP+.090*arch+extent
        if is_ace:
            z+=.27*arch
        previous=u
        xy=SOURCE[:2]*(1-u)+CATCH[:2]*u
        xy=xy+np.array((.07*ripple + sweep*(.28*u-.12+.10*math.sin(elapsed*TAU)),
                        -.60*math.sin(math.pi*u)+sweep*(.15*u-.08)+.044*arch*math.sin(index*.53)))
        if is_ace:
            xy[1]-=.19*arch
        xy += draw[:2]
        if load and cards:
            # The grip's bow is shared by neighboring sheets. Only the change
            # in their longitudinal coordinates costs extra vertical space.
            prior = cards[-1]
            slide = abs((xy-prior.center[:2]) @ heading[:2,1])
            shortening = .21 * abs(abs(bend) - abs(prior.bend))
            min_length = 1 - .42 * (GRIP_BOW + .105)
            z += 4 * abs(grip_bend) * (slide + shortening) / min_length
        ceiling = z + extent
        cards.append(Body(np.array((*xy,z)),basis,FACES[index],1,bend))
        states.append('caught' if raw>=1 else 'stock' if raw<=0 else 'air')
    # The still-squared cards share one printable stock edge. Every individual
    # card position can be recovered exactly from its packet center and pitch.
    visible=[]
    i=0
    while i<len(cards):
        j=i+1
        if states[i]!='air':
            while j<len(cards) and states[j]==states[i]:
                j+=1
        if j==i+1:
            visible.append(cards[i])
        else:
            visible.append(Body((cards[i].center+cards[j-1].center)/2,cards[i].rotation,FACES[j-1],j-i,cards[i].bend))
        i=j
    return visible,ceiling + .67*abs(grip_bend)


def deck(seconds):
    t=seconds % PERIOD
    cut_time,fold,stream=timeline(t)
    if stream:
        return spring(t-SPRING_START)
    if fold==1.:
        loading=t<SPRING_START
        if loading:
            load = spring_load(t-SPRING_START)
            center = SOURCE + GRIP_DRAW*load + (0., 0., -.21+PAPER_GAP+stock_depth(52)*.5)
            grip = rotation((0., 0., -17.-9.*load))
            stock = Body(center, grip, FACES[-1], 52, -GRIP_BOW*load)
            return [stock], center[2]+stock_depth(52)*.5+.67*abs(stock.bend)
        progress=(t-SPRING_START-SPRING_TIME)/CATCH_TIME
        pulse=math.sin(math.pi*min(1.,max(0.,progress)))**2
        bend=.090*pulse
        grip=rotation((-6*pulse,4*pulse,11))
        center=CATCH+np.array((0.,-.035*pulse,-.21+PAPER_GAP+stock_depth(52)*.5))
        stock=Body(center,grip,FACES[-1],52,bend)
        return [stock],center[2]+stock_depth(52)*.5+.67*abs(bend)
    bodies,top=concertina(cut_time,1-fold)
    if fold<=0:
        return bodies,top
    anchor=SOURCE if t<SPRING_START else CATCH
    basis=rotation((0,0,(-17 if t<SPRING_START else 11)*fold))
    return [Body(basis@p.center+anchor*fold,basis@p.rotation,p.face,p.count,p.bend) for p in bodies],top+anchor[2]*fold


def expand(bodies):
    cards=[]
    for group in bodies:
        for j in range(group.count):
            offset=(j-(group.count-1)*.5)*PITCH
            center=group.center+offset*group.rotation[:,2]
            cards.append(Body(center,group.rotation,FACES[len(cards)],1,group.bend))
    return cards


def optics(t):
    cut_time,fold,stream=timeline(t)
    _,a,cut,ribbon,fan,flip=score(cut_time)
    phase=TAU*(t%PERIOD)/PERIOD
    normal=np.array((-18+4*math.sin(a)-23*cut,-16+6*math.cos(a)+68*cut,-6+5*math.sin(a)-13*cut))
    envelope=math.sin(math.pi*(t-SPRING_START)/SPRING_TIME)**2 if stream else 0.
    cascade=np.array((35+5*math.sin(phase*2)+13*envelope,-8+7*math.cos(phase)+6*envelope,
                      -29+5*math.sin(phase)+7*envelope))
    cascade[0] -= 12 * spring_load(t%PERIOD - SPRING_START)
    basis=rotation(normal*(1-fold)+cascade*fold)
    return basis,cut,ribbon,math.sin(math.pi*flip)**2,fold,cut_time
