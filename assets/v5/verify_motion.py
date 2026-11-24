"""Check full-thickness stock, bowed flight paths, framing and the periodic join."""
from itertools import product

import numpy as np

from build_loop import FORMATS, FPS, project_stage
from card_geometry import CARD_WIDTH, STOCK
from packet_cut import PERIOD, PAPER_GAP, PITCH, PIVOT_START, PIVOT_END, SPRING_START, SPRING_TIME, deck, expand
from packet_cut import CUT_PERIOD, FAN_START, FAN_PEAK, FAN_END, FAN_PIN, FAN_STEP
from packet_cut import ACE_BACK_TIME, ACE_LEAVE, GRIP_BOW, LOAD_TIME, UNLOAD_TIME
from pack_order import FACES

CORNERS=np.array(list(product((-1.,1.),repeat=3)))


def boxes(cards):
    centers=np.array([c.center for c in cards])
    axes=np.array([c.rotation.T for c in cards])
    # The true quadratic bow stays inside this box, including its drawn edge.
    half=np.array([(CARD_WIDTH*.5,.5,c.thickness*.5+.67*abs(c.bend)) for c in cards])
    corners=np.einsum('nki,nij->nkj',CORNERS*half[:,None,:],axes)+centers[:,None,:]
    return centers,axes,half,corners


def separation(centers,axes,half):
    first,second=np.triu_indices(len(centers),k=1)
    if not len(first):
        return PAPER_GAP
    a,b=axes[first],axes[second]
    cross=np.cross(a[:,:,None,:],b[:,None,:,:]).reshape(-1,9,3)
    candidates=np.concatenate((a,b,cross),axis=1)
    norms=np.linalg.norm(candidates,axis=2,keepdims=True)
    unit=candidates/np.maximum(1e-12,norms)
    gap=np.abs(np.einsum('pki,pi->pk',unit,centers[first]-centers[second]))
    for basis,extent in ((a,half[first]),(b,half[second])):
        projected=np.abs(np.einsum('pki,pji->pkj',unit,basis))
        gap-=np.einsum('pkj,pj->pk',projected,extent)
    gap[norms[:,:,0]<1e-8]=-np.inf
    return float(np.max(gap,axis=1).min())


def visible_vertices(t):
    cards,top=deck(t)
    physical=expand(cards)
    _,_,_,corners=boxes(physical)
    return corners,top


def curved_packet_clearance(packets):
    """Measure the vertical gap between shared-heading bowed sheets over their overlap."""
    basis = packets[0].rotation
    centers = np.array([p.center @ basis for p in packets])
    lengths = np.array([1-.42*abs(p.bend) for p in packets])
    minimum = PAPER_GAP
    for j, upper in enumerate(packets):
        for i, lower in enumerate(packets[:j]):
            if abs(centers[j,0]-centers[i,0]) > CARD_WIDTH:
                continue
            lo = max(centers[i,1]-lengths[i]/2, centers[j,1]-lengths[j]/2)
            hi = min(centers[i,1]+lengths[i]/2, centers[j,1]+lengths[j]/2)
            if lo > hi:
                continue
            # Difference of the two parabolic surfaces. Its minimum lies at
            # an endpoint or where the two slopes agree.
            a, b = lower.bend / lengths[i]**2, upper.bend / lengths[j]**2
            ys = [lo, hi]
            if abs(b-a)>1e-12:
                ys.append(np.clip((b*centers[j,1]-a*centers[i,1])/(b-a),lo,hi))
            ys = np.asarray(ys)
            gap = centers[j,2]-centers[i,2] - (upper.thickness+lower.thickness)/2
            gap += 4*b*(ys-centers[j,1])**2 - 4*a*(ys-centers[i,1])**2 - .33*(upper.bend-lower.bend)
            minimum = min(minimum,float(gap.min()))
    return minimum


def check_spring_facing(packets, eye, seconds):
    basis = packets[0].rotation
    for card in packets:
        if seconds > ACE_LEAVE and card.count == 1 and card.face == FACES[-1]:
            continue
        if not np.allclose(card.rotation, basis, atol=1e-10, rtol=0):
            raise ValueError('A card changed its heading during the spring')
        # The dot product of the curved face normal and the ray to the eye
        # is quadratic along its length. Check both tips and its extremum.
        _, eye_y, eye_z = (eye - card.center) @ basis
        length = 1 - .42 * abs(card.bend)
        for v in (-.5, .5, np.clip(eye_y/length, -.5, .5)):
            facing = length * (eye_z - card.thickness/2 + card.bend*(.33 + 4*v*v))
            facing -= 8 * card.bend * eye_y * v
            if facing <= 0:
                raise ValueError(f'The camera sees the back of {card.face} during the spring')


def verify():
    minimum=1.; max_air=0; samples=6800
    minimum_trim={k:np.inf for k in FORMATS}
    assert abs(PITCH-STOCK-PAPER_GAP)<1e-12
    for t in np.linspace(0,PERIOD,samples,endpoint=False):
        packets,top=deck(t)
        if sum(p.count for p in packets)!=52:
            raise ValueError(f'Stock count changed at {t}')
        centers,axes,half,corners=boxes(packets)
        releasing = SPRING_START <= t < SPRING_START + UNLOAD_TIME
        clearance=curved_packet_clearance(packets) if releasing else separation(centers,axes,half)
        if clearance<.00012:
            raise ValueError(f'Packet intersection at {t:.5f}, clearance {clearance:.7f}')
        minimum=min(minimum,clearance,PAPER_GAP)
        max_air=max(max_air,sum(abs(c.bend)>1e-8 for c in packets))
        if SPRING_START <= t <= SPRING_START + SPRING_TIME:
            check_spring_facing(packets, project_stage('film',t,top=top).eye, t-SPRING_START)
        for key,((w,h),_,_,left) in FORMATS.items():
            xy,_=project_stage(key,t,top=top).project(corners.reshape(-1,3))
            header=94 if key=='mobile' else 0
            minimum_trim[key]=min(minimum_trim[key],xy[:,0].min(),xy[:,1].min()-header,
                                  w-left-xy[:,0].max(),h-xy[:,1].max())
    if min(minimum_trim.values())<3 or max_air<8:
        raise ValueError(f'Framing or spring flight lost: {minimum_trim}, {max_air}')
    eps=.00005
    for join in (0., SPRING_START - LOAD_TIME, SPRING_START, SPRING_START + UNLOAD_TIME, SPRING_START + SPRING_TIME,
                 SPRING_TIME + PIVOT_START, SPRING_TIME + PIVOT_END,
                 SPRING_TIME + CUT_PERIOD*FAN_START, SPRING_TIME + CUT_PERIOD*FAN_END):
        left=visible_vertices(join-eps)[0]
        now=visible_vertices(join)[0]
        right=visible_vertices(join+eps)[0]
        np.testing.assert_allclose((right-now)/eps,(now-left)/eps,atol=.005)
    np.testing.assert_allclose(visible_vertices(0)[0],visible_vertices(PERIOD)[0],atol=1e-10)
    squeezed = deck(SPRING_START)[0]
    assert len(squeezed)==1 and squeezed[0].count==52 and abs(squeezed[0].bend + GRIP_BOW)<1e-8
    releasing = deck(SPRING_START+.12)[0]
    assert len(releasing)>1 and releasing[-1].count>40 and abs(releasing[-1].bend)>.20
    caught, ace = deck(ACE_BACK_TIME)[0]
    assert caught.count==51 and ace.face==FACES[-1] and ace.rotation[2,2]<-.999
    leaves = expand(deck(SPRING_TIME + CUT_PERIOD*FAN_PEAK)[0])[-10:]
    pins = np.array([leaf.center + leaf.rotation @ FAN_PIN for leaf in leaves])
    np.testing.assert_allclose(pins[:, :2] - pins[0, :2], 0, atol=1e-9)
    for first, second in zip(leaves, leaves[1:]):
        relative = first.rotation.T @ second.rotation
        np.testing.assert_allclose(np.degrees(np.arctan2(relative[1,0], relative[0,0])), FAN_STEP, atol=1e-9)
    frames=np.arange(round(FPS*PERIOD))/FPS
    poses=[visible_vertices(t) for t in frames]
    for key in FORMATS:
        projected=[project_stage(key,t,top=top).project(points.reshape(-1,3))[0] for t,(points,top) in zip(frames,poses)]
        motion=np.sqrt(np.mean(np.sum((np.roll(projected,-1,axis=0)-projected)**2,axis=-1),axis=-1))
        print(f'{key}: margin {minimum_trim[key]:.2f}px, minimum movement {motion.min():.4f}px/frame')
        if motion.min()<.002:raise ValueError(f'Stalled at frame {motion.argmin()} in {key}')
    print(f'{samples} poses with a complete 52-card deck; {max_air} bowed cards simultaneously in flight; minimum clearance {minimum:.7f} heights.')


if __name__=='__main__':
    verify()
