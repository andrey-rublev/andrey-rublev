"""Fixed dealing order. Each printed rank and suit occurs exactly once."""
RANKS=("A","2","3","4","5","6","7","8","9","10","J","Q","K")
SUITS=("clubs","diamonds","hearts","spades")
RESERVED={
    2:("7","diamonds","seven-diamonds"),4:("2","clubs","two-clubs"),
    7:("10","spades","ten-spades"),10:("Q","spades","queen-spades"),
    29:("K","hearts","king-hearts"),41:("K","spades","king-spades"),
    48:("J","spades","jack-spades"),50:("Q","hearts","queen-hearts"),
    51:("A","spades","first-ace"),
}
def dealing_order():
    known={(rank,suit) for rank,suit,_ in RESERVED.values()}
    rest=[(rank,suit) for rank in RANKS for suit in SUITS if (rank,suit) not in known]
    # A coprime stride interleaves suits without relying on a random seed.
    order=iter([rest[(i*17+6)%len(rest)] for i in range(len(rest))])
    deck=[]
    for i in range(52):
        if i in RESERVED:deck.append(RESERVED[i])
        else:
            rank,suit=next(order)
            deck.append((rank,suit,f'{rank}-{suit}'))
    return deck

CARDS=dealing_order()
FACES=tuple(name for _,_,name in CARDS)
assert len({(rank,suit) for rank,suit,_ in CARDS})==52
