from itertools import product
from maslite import Agent, AgentMessage, Scheduler

__author__ = ["bjorn.madsen@operationsresearchgroup.com"]

__description__ = """
    INTRODUCTION
    This demo illustrates how to solve the assignment problem using
    OutScale and Dmitry Bertsekas Distributed Assignment Solving algorithm
    from 1979.

    It uses an optimization method that:
     - maximizes the total income for sellers, whilst,
     - minimizing total cost for buyers.

    It solves the problem as an alternating iterative auctions, where sellers
    and Buyers send messages to exchange information about the multi-lateral
    bidding process that identifies the optimal solution through iterations.

    Sellers send out sellers
    Buyers send bids

    The demo is thereby a batch-free optimization method, which allows the user
    to extend the dataset at any time, without having to restart the optimization
    process

    The demo also presents the convenience methods that an agent which operates
    as an agent-factory, can create an agent and send it to None. The mailman
    will detect that message isinstance(msg, Agent) and forward it to the
    scheduler. The scheduler will then add the agent correctly and assure it
    is updated.

    USER PROCESS
    The steps involved are:
    1. setup the scheduler
    2. launch biddata (which loads the sellers and buyers.)
    3. run!
    4. stop when the optimal solution has been found.

    CLASSES, RELATIONSHIPS AND GENERAL PROPERTIES:
    Trader: A general seller&buyer-agent that contains the negotiation process
    Seller: A subclass of Trader that only does the selling.
    Buyer: A subclass of Trader that only does the buying.
    Bid-database: An agent that imitates the database operation.
    AgentFactory: An agent that makes sellers and buyers based what is in the biddatabase.

    PROTOCOL:
    1. Buyer sends RFQ
    2. Seller react to RFQ by sending ADVERT with price (if price is not None).

    3. Seller sends ACCEPT to Buyer if the Buyer is the most attractive of all known RFQs.

    4. Buyer selects cheapest of the received ADVERTs that have been ACCEPTed by seller by sending ACCEPT, 
       Buyer WITHDRAWs from all others.

    5. Seller receiving ACCEPT enter contract.
       Sellers receiving WITHDRAW resets any sent ACCEPT and sends ACCEPT for the next best RFQ.

    6. Buyers receiving ACCEPT  


"""

buyer_data = {  # buyer id: budget limit for purchase.
    100: 400, 101: 410, 102: 300, 103: 330,
    104: 250, 105: 300, 106: 400, 107: 300,
    108: 300, 109: 300, 110: 300, 111: 300,
    112: 250}
seller_data = {  # seller id and cost of job for buyer id{1,2,3,...}
    0: {100: None, 101: 288.88, 102: 211.97, 103: 334.97, 104: None, 105: None, 106: 341.76, 107: 211.5, 108: 221.47,
        109: 259.09, 110: None, 111: None, 112: None, },
    1: {100: None, 101: None, 102: None, 103: None, 104: None, 105: None, 106: 351.35, 107: 236.61, 108: 246.57,
        109: 284.2, 110: None, 111: None, 112: None, },
    2: {100: None, 101: None, 102: None, 103: None, 104: None, 105: 239.73, 106: None, 107: None, 108: None, 109: None,
        110: None, 111: None, 112: None, },
    3: {100: None, 101: None, 102: None, 103: None, 104: None, 105: None, 106: 334.96, 107: 256.28, 108: 258.65,
        109: 267.8, 110: None, 111: None, 112: None, },
    4: {100: 316.55, 101: None, 102: None, 103: None, 104: None, 105: None, 106: None, 107: None, 108: None, 109: None,
        110: None, 111: None, 112: None, },
    5: {100: None, 101: 281.8, 102: 251.68, 103: 327.89, 104: None, 105: None, 106: 287.19, 107: 225.73, 108: 228.1,
        109: 218.94, 110: 251.26, 111: 197.73, 112: 244.9, },
    6: {100: None, 101: 305.67, 102: 228.76, 103: 351.76, 104: None, 105: None, 106: 311.05, 107: 195.22, 108: 205.18,
        109: 242.81, 110: 220.75, 111: 221.6, 112: 221.98, },
    7: {100: None, 101: 289.27, 102: 240.84, 103: 335.36, 104: None, 105: None, 106: 294.66, 107: 214.89, 108: 217.26,
        109: 226.41, 110: 240.42, 111: 205.2, 112: 234.06, },
    8: {100: None, 101: 265.01, 102: 234.89, 103: 311.1, 104: None, 105: None, 106: 317.89, 107: 242.01, 108: 244.38,
        109: 235.22, 110: None, 111: None, 112: None, },
    9: {100: None, 101: 272.48, 102: 224.05, 103: 318.57, 104: None, 105: None, 106: 325.36, 107: 231.17, 108: 233.54,
        109: 242.69, 110: None, 111: None, 112: None, },
    10: {100: None, 101: None, 102: None, 103: None, 104: 230.63, 105: None, 106: None, 107: None, 108: None, 109: None,
         110: None, 111: None, 112: None, },
}

assert set(seller_data.keys()).isdisjoint(set(buyer_data.keys())), "there's an overlap in uuids."


class RFQ(AgentMessage):
    def __init__(self, sender, max_price, receiver=None):
        assert isinstance(sender, Buyer)
        if receiver is None:
            receiver = Seller.__name__
        super().__init__(sender=sender, receiver=receiver)
        self.max_price = max_price


class Advert(AgentMessage):
    def __init__(self, sender, receiver=None, price=None):
        assert isinstance(sender, Seller)
        if receiver is None:
            receiver = Buyer.__name__
        super().__init__(sender=sender, receiver=receiver)
        self.price = price


class Accept(AgentMessage):  # bid acceptance
    def __init__(self, sender, receiver):
        super().__init__(sender=sender, receiver=receiver)


class Withdraw(AgentMessage):
    def __init__(self, sender, receiver):
        super().__init__(sender=sender, receiver=receiver)


class Seller(Agent):
    def __init__(self, uid, prices, send_advert_at_setup=True):
        super().__init__(uuid=uid)
        self.operations[RFQ.__name__] = self.rfq
        self.operations[Accept.__name__] = self.acc
        self.operations[Withdraw.__name__] = self.withdraw
        self.buyers = {}
        self.prices = prices
        self.send_advert_at_setup = send_advert_at_setup

    def setup(self):
        if self.send_advert_at_setup:
            self.send(Advert(sender=self))

    def update(self):
        while self.messages:
            msg = self.receive()
            ops = self.operations.get(msg.topic)
            ops(msg)

        # make up my mind.
        offers = []
        for buyer in self.buyers:
            price = self.buyers[buyer]['price']
            offers.append([price, buyer])
        offers.sort(reverse=True)  # biggest first.

        tender_closed = False
        for offer in offers:
            price, buyer = offer
            if tender_closed:
                if not self.buyers[buyer]['withdrawn']:
                    self.send(Withdraw(sender=self, receiver=buyer))
                    self.buyers[buyer]['withdrawn'] = True
                    self.buyers[buyer]['selected'] = False
                continue
            if self.buyers[buyer]['withdrawn']:
                continue
            if self.buyers[buyer]['accepted']:
                self.send(Accept(sender=self, receiver=buyer))
                self.buyers[buyer]['selected'] = True
                tender_closed = True
            elif not self.buyers[buyer]['accepted']:
                pass  # wait for response.

    def teardown(self):
        pass

    def rfq(self, msg):
        assert isinstance(msg, RFQ)
        if msg.sender in self.buyers:
            return
        price = self.prices.get(msg.sender, None)
        if price is None:
            return
        if msg.max_price < price:
            return
        self.buyers[msg.sender] = {'price': price, 'accepted': None, 'selected': None, 'withdrawn': False}
        self.send(Advert(sender=self, receiver=msg.sender, price=price))

    def acc(self, msg):
        assert isinstance(msg, Accept)
        self.buyers[msg.sender]['accepted'] = True
        self.buyers[msg.sender]['withdrawn'] = False

    def withdraw(self, msg):
        assert isinstance(msg, Withdraw)
        self.buyers[msg.sender]['accepted'] = False
        self.buyers[msg.sender]['selected'] = False
        self.buyers[msg.sender]['withdrawn'] = True

    def in_contract_with(self):
        for k, v in self.buyers.items():
            if v['selected']:
                return k


class Buyer(Agent):
    def __init__(self, uid, max_price, send_rfq_at_setup=True):
        super().__init__(uuid=uid)
        self.max_price = max_price
        self.operations[Advert.__name__] = self.adv
        self.operations[Accept.__name__] = self.acc
        self.operations[Withdraw.__name__] = self.withdraw
        self.sellers = {}
        self.send_rfq_at_setup = send_rfq_at_setup

    def setup(self):
        if self.send_rfq_at_setup:
            self.send(RFQ(sender=self, max_price=self.max_price))

    def update(self):

        while self.messages:
            msg = self.receive()
            ops = self.operations.get(msg.topic)
            ops(msg)

        # make up my mind.
        offers = []
        for seller in self.sellers:
            price = self.sellers[seller]['price']
            offers.append([price, seller])
        offers.sort()

        rfq_closed = False

        for offer in offers:
            price, seller = offer
            if rfq_closed:
                if not self.sellers[seller]['withdrawn']:
                    self.send(Withdraw(sender=self, receiver=seller))
                    self.sellers[seller]['withdrawn'] = True
                continue

            if self.sellers[seller]['accepted'] is None:
                self.send(Accept(sender=self, receiver=seller))
                self.sellers[seller]['selected'] = True
                rfq_closed = True
                continue
            if not self.sellers[seller]['accepted']:  # acceptance from seller is pending.
                continue  # wait for response.
                # accept is processed here.
                # withdraw is processed in self.withdraw
            else:  # accepted by seller.
                if self.sellers[seller]['selected']:  # selected by buyer. Nothing needs to change.
                    rfq_closed = True
                else:
                    self.send(Accept(sender=self, receiver=seller))
                    self.sellers[seller]['selected'] = True
                    rfq_closed = True

    def teardown(self):
        pass

    def adv(self, msg):
        assert isinstance(msg, Advert)
        if msg.price is None:
            self.send(RFQ(sender=self, receiver=msg.sender, max_price=self.max_price))
            return
        if msg.sender in self.sellers:
            return
        if msg.price <= self.max_price:
            self.sellers[msg.sender] = {'price': msg.price, 'accepted': None, 'selected': False, 'withdrawn': False}
        else:
            self.send(Withdraw(sender=self, receiver=msg.sender))

    def acc(self, msg):
        assert isinstance(msg, Accept)
        self.sellers[msg.sender]['accepted'] = True
        self.sellers[msg.sender]['withdrawn'] = False

    def withdraw(self, msg):
        assert isinstance(msg, Withdraw)
        self.sellers[msg.sender]['accepted'] = False
        self.sellers[msg.sender]['selected'] = False
        self.sellers[msg.sender]['withdrawn'] = True

    def in_contract_with(self):
        for k, v in self.sellers.items():
            if v['selected']:
                return k
        return False


def demo(sellers=None, buyers=None, time_limit=True,
         seller_can_initialise=True, buyer_can_initialise=True):
    """
    This demo() function was the first piece of code written in this
    python script. The simplicity of the demo forced the dev
    process to target a linear execution model.
    """
    if sellers is None:
        sellers = []
    if buyers is None:
        buyers = []

    s = Scheduler()
    for uuid in sellers:
        agent = Seller(uuid, prices=seller_data[uuid], send_advert_at_setup=seller_can_initialise)
        s.add(agent)
    for uuid in buyers:
        agent = Buyer(uuid, max_price=buyer_data[uuid], send_rfq_at_setup=buyer_can_initialise)
        s.add(agent)

    if time_limit:
        s.run(seconds=1)
    else:
        s.run(pause_if_idle=True)

    contracts = {}
    for uuid, agent in s.agents.items():
        if not isinstance(agent, (Buyer, Seller)):
            continue
        if agent.in_contract_with() is False:
            contracts[agent.uuid] = None
        else:
            contracts[agent.uuid] = agent.in_contract_with()

    print("", flush=True)
    print("Contracts at end:")
    for k, v in contracts.items():
        print("{}: {}".format(k, v), flush=True)
    assert len(contracts) > 0, "no contracts? That can't be true"
    return contracts


def test02():
    sellers = [4]
    buyers = [100]
    results = demo(sellers, buyers, time_limit=False)
    expected_results = {100: 4, 4: 100}
    for k, v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def test03():
    expected_results = {101: 5, 5: 101, 6: None, 7: None}
    sellers = [k for k in expected_results if k < 100]
    buyers = [k for k in expected_results if k >= 100]
    results = demo(sellers, buyers)
    for k, v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def test04():
    expected_results = {0: 101, 101: 0, 102: None,
                        103: None}  # result: 0 enters contract with price 334.97 (the highest price)
    sellers = [k for k in expected_results if k < 100]
    buyers = [k for k in expected_results if k >= 100]
    results = demo(sellers, buyers)
    for k, v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def test05():
    expected_results = {101: 7, 102: 6, 103: 5, 5: 103, 6: 102, 7: 101}
    sellers = [k for k in expected_results if k < 100]
    buyers = [k for k in expected_results if k >= 100]
    results = demo(sellers, buyers)
    for k, v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def test06():
    expected_results = {0: 108,
                        1: 107,
                        2: 105,
                        3: None,
                        4: 100,
                        5: 106,
                        6: 109,
                        7: 102,
                        8: 103,
                        9: 101,
                        10: 104,
                        100: 4,
                        101: 9,
                        102: 7,
                        103: 8,
                        104: 10,
                        105: 2,
                        106: 5,
                        107: 1,
                        108: 0,
                        109: 6,
                        110: None,
                        111: None,
                        112: None}
    sellers = [k for k in expected_results if k < 100]
    buyers = [k for k in expected_results if k >= 100]
    error_sets = []

    for s_init, b_init in list(product([True, False], repeat=2)):
        if not s_init and not b_init:
            continue  # if neither seller or buyer initialise, obviously nothing will happen.
        results = demo(sellers=sellers, buyers=buyers, seller_can_initialise=s_init, buyer_can_initialise=b_init)
        errors = []
        for k, v in results.items():
            if not expected_results[k] == v:  # , "Hmmm... That's not right {}={}".format(k, v)
                errors.append((k, v))
        if errors:
            error_sets.append(errors)
    if error_sets:
        print("-" * 80)
        for i in error_sets:
            print(",".join(str(i) for i in sorted(i)), flush=True)
        raise AssertionError("output does not reflect expected results.")


def do_all():
    for k, v in sorted(globals().items()):
        if k.startswith("test") and callable(v):
            v()
            print(k, "done")


if __name__ == "__main__":
    do_all()

