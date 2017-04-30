import time
import logging
from outscale.core import Agent, AgentMessage, AddNewAgent, SubscribeMessage, Scheduler
from collections import deque
from operator import attrgetter

__author__ = ["bjorn.h.madsen@gmail.com",
              "bjorn.madsen@operationsresearchgroup.com",
              "bjorn.madsen@dematic.com"]

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

    WHAT HAPPENS:
    1. The scheduler launches the Tracker and sends an authorised StopMessage to it.
    2. The AgentFactory gets a message from the Bid-database to create N buyers and M sellers.
    3. The Seller & Buyer agents negotiate and once contracts are made, the subscribing Tracker notices.
"""


class GetPrice(AgentMessage):
    """
    This message is used by the seller, to obtain the cost of serving the buyer,
    which is hidden to the seller.
    """
    def __init__(self, sender, partner_id):
        super().__init__(sender=sender, receiver=BidDatabase.__name__, topic=self.__class__.__name__)
        self.partner_id = partner_id

    def get_partner_id(self):
        return self.partner_id


class SetPrice(AgentMessage):
    """
    This message is used by the bid database to respond to the seller with a
    price to server the particular partner.
    """
    def __init__(self, sender, receiver, price, partner_id):
        super().__init__(sender=sender, receiver=receiver)
        self.price = price
        self.partner_id = partner_id

    def get_price(self):
        return self.price

    def get_partner_id(self):
        return self.partner_id


class NewAgentRegister(AgentMessage):
    def __init__(self, sender, receiver,agent_register):
        super().__init__(sender=sender, receiver=receiver)
        self.agent_register = agent_register

    def get_agent_register(self):
        return self.agent_register


class BidDatabase(Agent):
    def __init__(self, sellers=[], buyers=[]):
        super().__init__()
        self.buyers = {  # id: max_price
            0: 400, 1: 410, 2: 300, 3: 330, 4: 250, 5: 300, 6: 400, 7: 300, 8: 300, 9: 300, 10: 300, 11: 300, 12: 250}
        self.sellers = {  # id: (req_id=0 cost, req_id=1 cost, .... req_id=N cost), ...
            0: (  None, 288.88, 211.97, 334.97,   None,   None, 341.76, 211.50, 221.47, 259.09,   None,   None,   None),
            1: (  None,   None,   None,   None,   None,   None, 351.35, 236.61, 246.57, 284.20,   None,   None,   None),
            2: (  None,   None,   None,   None,   None, 239.73,   None,   None,   None,   None,   None,   None,   None),
            3: (  None,   None,   None,   None,   None,   None, 334.96, 256.28, 258.65, 267.80,   None,   None,   None),
            4: (316.55,   None,   None,   None,   None,   None,   None,   None,   None,   None,   None,   None,   None),
            5: (  None, 281.80, 251.68, 327.89,   None,   None, 287.19, 225.73, 228.10, 218.94, 251.26, 197.73, 244.90),
            6: (  None, 305.67, 228.76, 351.76,   None,   None, 311.05, 195.22, 205.18, 242.81, 220.75, 221.60, 221.98),
            7: (  None, 289.27, 240.84, 335.36,   None,   None, 294.66, 214.89, 217.26, 226.41, 240.42, 205.20, 234.06),
            8: (  None, 265.01, 234.89, 311.10,   None,   None, 317.89, 242.01, 244.38, 235.22,   None,   None,   None),
            9: (  None, 272.48, 224.05, 318.57,   None,   None, 325.36, 231.17, 233.54, 242.69,   None,   None,   None),
            10:(None,   None,   None,   None, 230.63,   None,   None,   None,   None,   None,   None,   None,   None),
        }
        self.operations.update({AddNewAgent.__name__: self.new_agent_message,
                                GetPrice.__name__: self.lookup_price})

        self.agent_register = {}
        if sellers == []:
            self.whitelisted_sellers = list(self.sellers.keys())
        else:
            list_of_sellers = sorted(self.sellers.keys())
            self.whitelisted_sellers = [idx for idx in sellers if idx in list_of_sellers]

        if buyers == []:
            self.whitelisted_buyers = list(self.buyers.keys())
        else:
            list_of_buyers = sorted(self.buyers.keys())
            self.whitelisted_buyers = [idx for idx in buyers if idx in list_of_buyers]


    def setup(self):
        """ 1) First the database subscribes to new agent messages, so that it can create
        a dictionary with created agents uuid and it's own naming methodology."""
        sub_msg = SubscribeMessage(sender=self, subscription_topic=AddNewAgent.__name__)
        self.send(sub_msg)

        for seller_name, price_range in self.sellers.items():
            if seller_name in self.whitelisted_sellers:
                msg = MakeAgent(sender=self, receiver=AgentFactory.__name__,
                                agent_to_be_created=Seller, name=seller_name)
                self.send(msg)

        for buyer_name, max_price in self.buyers.items():
            if buyer_name in self.whitelisted_buyers:
                msg = MakeAgent(sender=self, receiver=AgentFactory.__name__,
                                agent_to_be_created=Buyer, name=buyer_name, max_price=max_price)
                self.send(msg)

    def update(self):
        while self.messages:
            msg = self.receive()
            operation = self.operations.get(msg.topic)
            if operation is not None:
                operation(msg)
            else:
                self.logger("%s %s: don't know what to do with: %s" %
                            (self.__class__.__name__, str(self.uuid)[-6:], str(msg)),
                            log_level="DEBUG")

    def teardown(self):
        pass

    def new_agent_message(self, msg):
        """
        ! The example below is important as it does not keep a reference
        to the agent object, but tracks the id's itself.

        This is important because when the agent is pickled so that it can
        be sent between multiprocessors using Queues all references are broken.

        The alternative is that the whole context is shipped which will have
        unpredictable side effects.

        :param msg: AddNewAgent message
        :return: None
        """
        assert isinstance(msg, AddNewAgent)
        agent = msg.agent

        _uuid = agent.uuid
        _type = agent.__class__.__name__
        _name = agent.get_name()

        for item in (_uuid, _type, _name):
            assert isinstance(item, (str, int)), "Cannot store references to agents"
        self.agent_register[_uuid] = (_type, _name)

    def lookup_price(self, msg):
        assert isinstance(msg, GetPrice)
        sender = msg.sender
        partner_id = msg.get_partner_id()
        try:
            trader_type, name = self.agent_register[sender]
            partner_type, partner_index = self.agent_register[partner_id]
            if trader_type == Seller.__name__:
                price = self.sellers[name][partner_index]
                msg = SetPrice(sender=self, receiver=sender, price=price, partner_id=partner_id)
                self.send(msg)
            elif trader_type == Buyer.__name__:  # this is logical to add for completeness, but will not be needed...
                # ...because the buyer will use the RFQ to ask the seller for a price.
                price = self.buyers[name][partner_index]
                msg = SetPrice(sender=self, receiver=sender, price=price, partner_id=partner_id)
                self.send(msg)
        except KeyError:
            raise KeyError("This partner should already exist.")


# ------- Agent Factory -------


class MakeAgent(AgentMessage):
    def __init__(self, sender, receiver, agent_to_be_created, **kwargs):
        super().__init__(sender=sender, receiver=AgentFactory.__name__, topic=self.__class__.__name__)
        self.agent_to_be_created = agent_to_be_created
        self.agent_init_args = kwargs

    def get_type(self):
        return self.agent_to_be_created

    def get_init_args(self):
        return self.agent_init_args


class AgentFactory(Agent):
    """
    The agent factory is an agent that subscribes to messages that request
    the construction of new agents and add them to the scheduler.

    To remove/destroy agents at runtime, see core.RemoveAgent.
    """
    def __init__(self):
        super().__init__()
        self.operations.update({MakeAgent.__name__: self.make_agent})

    def setup(self):
        """ The agent factory subscribes to broadcast concerning "MakeAgent"... """
        sub_msg = SubscribeMessage(sender=self, subscription_topic=MakeAgent.__name__)
        self.send(sub_msg)

    def update(self):
        while self.messages:
            msg = self.receive()
            operation = self.operations.get(msg.topic)
            if operation is not None:
                operation(msg)
            else:
                self.logger("%s %s: don't know what to do with: %s" %
                            (self.__class__.__name__, str(self.uuid)[-6:], str(msg)),
                            log_level="DEBUG")

    def teardown(self):
        pass

    def make_agent(self, msg):
        assert isinstance(msg, MakeAgent)
        agent_class = msg.get_type()
        kwargs = msg.get_init_args()
        agent = agent_class(**kwargs)  # make the agent with variable length init arguments
        msg = AddNewAgent(sender=self, agent=agent)  # send the agent to the scheduler
        self.send(msg)
        # The scheduler makes sure, that agents always are attached to the mainloop.

# -------- Trader messages ---------


class Advertisement(AgentMessage):
    def __init__(self, sender, receiver=None):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)


class RequestForQuotation(AgentMessage):
    def __init__(self, sender, max_price, receiver=None):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)
        self.max_price = max_price

    def get_max_price(self):
        return self.max_price


class OfferDocument(AgentMessage):
    def __init__(self, sender, receiver, bid_price):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)
        self.bid_price = bid_price

    def get_bid_price(self):
        return self.bid_price


class Acceptance(AgentMessage):  # bid acceptance
    def __init__(self, sender, receiver):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)


class Contract(AgentMessage):
    def __init__(self, sender, receiver):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)


class ContractConfirmation(AgentMessage):
    def __init__(self, sender, receiver):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)


class Recall(AgentMessage):  # contract recall
    def __init__(self, sender, receiver):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)


class Commit(AgentMessage):
    def __init__(self, sender, receiver):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)


class Opportunity(object):
    """
    This class is a data structure for the negotiation process.
    """
    __slots__ = ("price", "time", "partner_id", "price_acceptance", "contract_exchanged", "contract_confirmed")

    def __init__(self, partner_id, price, time):
        self.price = price
        self.time = time
        self.partner_id = partner_id
        self.price_acceptance = False
        self.contract_exchanged = False
        self.contract_confirmed = False

    def __repr__(self):
        d = {'price': self.price,
             'time': self.time,
             'partner_id': self.partner_id,
             'price_acceptance': self.price_acceptance,
             'contract_exchanged': self.contract_exchanged,
             'contract_confirmed': self.contract_confirmed}
        s = []
        for k in self.__slots__:
            s.append("{}:{}".format(k,d[k]))
        return "{%s}" % ", ".join(s)

    def __str__(self):
        return repr(self)

    def __lt__(self, other):
        if self.price < other.price:
            return True
        elif self.price == other.price:
            if self.time < other.time:
                return True
            elif self.time == other.time:
                if self.partner_id < other.partner_id:  # this is guaranteed to be unique.
                    return True
        return False

    def __gt__(self, other):
        if not self < other:
            return True


class Trader(Agent):
    """
    The Trader class supports the alternating iterative auction by
    implementing the following process.

    The agent lifecycle elapses as:
    1) setup, where it initiates the conversation.
    2) update, where the operations dictionary implements the finite state
    diagram of the agent negotiation. At every update the agent will:
       a) receive all messages to prioritize the "commit" message above anything else.
       b) receive and log all new opportunities.
       c) compare all known opportunities and send out a minimal number of messages.
    3) teardown, which is triggered by the commit message.

    """
    def __init__(self):
        super().__init__()
        # Below works as: if agent receives topic='key' then respond with function='value'.
        self.operations.update({Advertisement.__name__:        self.log_opportunity,  # if receiving an 'advertisement' then send out a 'request for quotation'
                                RequestForQuotation.__name__:  self.log_opportunity,  # if receiving a 'request for qoutation': then send out a ('bid', 'no bid'). Note that  'no bid' is silent
                                SetPrice.__name__:             self.log_opportunity,
                                OfferDocument.__name__:        self.log_opportunity,  # if 'bid' then respond ('bid acceptance', 'no acceptance'). Note that 'no acceptance' is silent
                                Acceptance.__name__:           self.log_opportunity,  # if 'bid acceptance' then respond ('contract', 'contract recall'),
                                Contract.__name__:             self.log_opportunity,  # if 'contract' then ('contract confirmation', 'contract confirmation recall'),
                                ContractConfirmation.__name__: self.log_opportunity,
                                Recall.__name__:               self.log_opportunity,  # if receiving a 'contract recall' then don't respond, but do update own state.
                                Commit.__name__:               self.commit})          # if receiving a 'commit' then leave the negotiation in current state.
        # The sub classed agent now only needs to know how to initialize the conversation
        # to respond correctly. The finite state diagram resolves the rest.
        self.opportunities = []
        self.fixed_price = None
        self.in_contract_with = None

    def setup(self):
        if isinstance(self, Seller):
            # start with sending an advertisement broadcasts to all Buyers.
            msg = Advertisement(sender=self, receiver=Buyer.__name__)  # broadcast
            self.send(msg)
        elif isinstance(self, Buyer):
            # start with sending a RFQ broadcast to all Sellers.
            msg = RequestForQuotation(sender=self, receiver=Seller.__name__, max_price=self.fixed_price)
            self.send(msg)
        else:
            raise NotImplementedError("Trader must run as either Seller or Buyer. The class Trader can not on its own.")

    def update(self):
        if self.messages:
            # 1) first, the priority inbox is implemented to take commit messages prior to any other message.
            new_messages = True
            priority_topics = {Commit.__name__}  # just this one for now...
            priority_messages = deque()
            normal_messages = deque()
            while self.messages:
                msg = self.receive()
                if msg.topic in priority_topics:
                    priority_messages.append(msg)
                else:
                    normal_messages.append(msg)
            priority_messages.extend(normal_messages)
            messages = priority_messages

            # 2) Okay - if there are any priority messages they'll be up front.
            while len(messages) > 0:        # equivalent to: while self.messages():
                msg = messages.popleft()    # equivalent to:     msg = self.receive()
                operation = self.operations.get(msg.topic)
                if operation is not None:
                    operation(msg)
                else:
                    self.logger("%s %s: don't know what to do with: %s" % (self.__class__.__name__, str(self.uuid)[-6:], str(msg)),
                                log_level="DEBUG")

            # 3) Now as all information has been received, the agent evaluates the information
            #    and produces a minimal response. However there is no reason to do this check
            #    if there were no messages...
            self.compare_opportunities()

    def teardown(self):
        pass

    def log_opportunity(self, msg):
        opportunity = self.get_opportunity(msg.sender)  #NB: Can be None.

        if isinstance(msg, Advertisement):  # seller advertises, buyer receives advertisement. Buyer then responds...
            msg = RequestForQuotation(sender=self, receiver=msg.sender, max_price=self.fixed_price)
            self.send(msg)
        elif isinstance(msg, RequestForQuotation):  # seller gets an RFQ, logs it and gets the price.
            if opportunity is None:
                opportunity = Opportunity(partner_id=msg.sender, price=None, time=self.time)
                self.opportunities.append(opportunity)
                self.get_price(msg.sender)
            else:  # it's a duplicate request
                pass
        elif isinstance(msg, SetPrice):   # seller gets the price, updates the opportunity and sends offer to buyer
            opportunity = self.get_opportunity(msg.get_partner_id())
            if opportunity.price is None:
                if msg.get_price() is None:
                    send_offer_doc = False  # then it is a no-bid. No need to do anything.
                else:
                    opportunity.price = msg.get_price()
                    send_offer_doc = True
            else:
                if opportunity.price == msg.get_price():  # then it's a duplicate caused by async timing.
                    send_offer_doc = False
                else:  # it's a price update.
                    send_offer_doc = True
            if send_offer_doc:
                    msg = OfferDocument(sender=self, receiver=msg.get_partner_id(), bid_price=msg.get_price())
                    self.send(msg)
        elif isinstance(msg, OfferDocument):  # buyer receives the offer document...
            if opportunity:  # if the opportunity exists, then it's a price update.
                opportunity.price, opportunity.time = msg.get_bid_price(), self.time
            else:  # then it's a new opportunity.
                opportunity = Opportunity(price=msg.get_bid_price(), partner_id=msg.sender, time=self.time)
                self.opportunities.append(opportunity)
            # buyer can now choose to send the acceptance if the offer document contains the best offer.
        elif isinstance(msg, Acceptance):  # seller get's buyers acceptance to the offer document
            opportunity.price_acceptance = True
            # seller can now choose to send the contract if the buyer is the best option.
        elif isinstance(msg, Contract):  # buyer get's a contract to review / seller get's a contract acceptance.
            opportunity.contract_exchanged = True
        elif isinstance(msg, ContractConfirmation):
            opportunity.contract_confirmed = True
        elif isinstance(msg, Recall):
            opportunity.contract_exchanged = False
            opportunity.contract_confirmed = False
            if self.in_contract_with == msg.sender:
                self.in_contract_with = None
        else:
            raise NotImplementedError("The following message was received as an opportunity, but no method is in place to handle it:\n{}".format(str(msg)))

    def sort_opportunities(self):
        raise NotImplementedError("The subclasses Buyer & Seller must implement the method: sort_opportunities.")

    def compare_opportunities(self):
        # 1) first opportunities are sorted
        # 2) next the best opportunity is selected for contract.
        raise NotImplementedError("The subclasses Buyer & Seller must implement these.")

    def get_opportunity(self, partner_id):
        for opportunity in self.opportunities:
            assert isinstance(opportunity, Opportunity)
            if opportunity.partner_id == partner_id:
                return opportunity
        return None

    # agent reactions upon receipt of messages
    def advertisement(self, msg):
        msg = RequestForQuotation(sender=self, receiver=msg.sender, max_price=self.fixed_price)
        self.send(msg)

    def get_price(self, partner_id):
        msg = GetPrice(sender=self, partner_id=partner_id)
        self.send(msg)

    def commit(self, msg):
        raise NotImplementedError


class Seller(Trader):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def get_name(self):
        return self.name

    def sort_opportunities(self):
        """
        Below the decorate-sort-undecorate method is used
        (https://wiki.python.org/moin/HowTo/Sorting#The_Old_Way_Using_Decorate-Sort-Undecorate)
        The method creates tuples that contain the original listed opportunity together
        with the price and negative time. The reverse sort assures that the highest price
        comes on top, whilst the negative time assures that the first received
        opportunity comes out first in case two opportunities have the same price.
        Finally the partner_id is used to cover the case where the CPU clock resolution is
        insufficient to determine which opportunity arrived first.
        """
        known_prices, prices_with_none = [],[]
        for o in self.opportunities:
            if o.price is None:
                prices_with_none.append(o)
            else:
                known_prices.append(o)
        decorated = [(o.price, -o.time, -o.partner_id, o) for o in known_prices]
        decorated.sort(reverse=True)
        self.opportunities = [o for price, time, partner, o in decorated]
        self.opportunities.extend(prices_with_none)

    def compare_opportunities(self):
        best_contract_in_place = False
        self.sort_opportunities()  # this sort assures that the best bid is on top.
        for opportunity in self.opportunities:
            assert isinstance(opportunity, Opportunity)
            if opportunity.price is None:
                continue  # ignore.
            if not opportunity.price_acceptance:
                continue  # ignore
            if not opportunity.contract_exchanged:   # then send the contract immediately as:
                # a) it's the best opportunity.
                # b) the price was accepted.
                if not best_contract_in_place:
                    msg = Contract(sender=self, receiver=opportunity.partner_id)
                    self.send(msg)
                    opportunity.contract_exchanged = True
            if opportunity.contract_confirmed:
                if self.in_contract_with == opportunity.partner_id:
                    best_contract_in_place = True  # everything is as it should be.
                else:  # if self.in_contract_with != opportunity.partner_id:
                    if self.in_contract_with is None:  # then it's the first valid contract.
                        # assert not best_contract_in_place
                        self.in_contract_with = opportunity.partner_id
                        best_contract_in_place = True
                    # partner is better, but
                    else:  # if self.in_contract_with is not None:
                        if not best_contract_in_place:
                            self.in_contract_with = opportunity.partner_id
                            best_contract_in_place = True
                        else:  # best_contract_in_place == True
                            # partner is lesser, but has confirmed.
                            msg = Recall(sender=self, receiver=opportunity.partner_id)
                            self.send(msg)
                            opportunity.contract_exchanged = False
                            opportunity.contract_confirmed = False
            # At this point in the execution path, either:
            # a) The price has not been accepted, or,
            # b) The contract has not been confirmed.
            # The seller should thereby move on to the next best option...
            continue

    def update(self):
        super().update()


class Buyer(Trader):
    def __init__(self, name, max_price):
        super().__init__()
        self.name = name
        self.set_maximum_price(max_price)

    def set_maximum_price(self, price):
        self.fixed_price = price

    def get_name(self):
        return self.name

    def sort_opportunities(self):
        """
        The usage of attrgetter is explained in:
        https://wiki.python.org/moin/HowTo/Sorting#Sort_Stability_and_Complex_Sorts
        which works as the sort is the same direction (descending) for all three properties.
        if the direction wasn't the same, the decorate-sort-undecorate method would be required.
        """
        decorated = [(o.price, o.time, o.partner_id, o) for o in self.opportunities]
        decorated.sort()
        self.opportunities = [o for price, time, partner, o in decorated]

    def compare_opportunities(self):
        best_partner_found = False
        self.sort_opportunities()  # this sort assures that the best bid is on top.
        for opportunity in self.opportunities:
            assert isinstance(opportunity, Opportunity)
            if opportunity.price <= self.fixed_price:
                if not opportunity.price_acceptance:
                    opportunity.price_acceptance = True
                    msg = Acceptance(sender=self, receiver=opportunity.partner_id)
                    self.send(msg)
                    continue
                elif not opportunity.contract_exchanged:
                    continue  # we're waiting for a contract, so we pick the next best offer until it arrives.
                elif not opportunity.contract_confirmed:
                    if not best_partner_found:  # respond immediately as the first on the list is the best offer...
                        opportunity.contract_confirmed = True
                        msg = ContractConfirmation(sender=self, receiver=opportunity.partner_id)
                        self.send(msg)
                        if self.in_contract_with is None:
                            self.in_contract_with = opportunity.partner_id
                            best_partner_found = True
                            continue
                        elif self.in_contract_with != opportunity.partner_id:
                            msg = Recall(sender=self, receiver=self.in_contract_with)
                            self.send(msg)
                            old_opportunity = self.get_opportunity(self.in_contract_with)
                            old_opportunity.contract_confirmed = False
                            old_opportunity.contract_exchanged = False
                            self.in_contract_with = opportunity.partner_id
                            best_partner_found = True
                    elif best_partner_found:
                        continue  # Keep quiet... It's nice to have potential partners.

    def update(self):
        super().update()


def test01():
    """sortation test"""
    o1 = Opportunity(partner_id=1, price=3, time=time.time())
    print("sample opportunity is printed below to exercise the __str__ method:")
    print(o1)
    o2 = Opportunity(partner_id=2, price=3, time=time.time())
    o3 = Opportunity(partner_id=3, price=4, time=time.time())
    o4 = Opportunity(partner_id=4, price=2, time=time.time())
    L = [o1,o2,o3,o4]
    # single step filter to get the lowest price at earliest time up on top.
    s = sorted(L, key=attrgetter('price', 'time'))
    assert s == [o4,o1,o2,o3], "sorting should have produced this result..."  # Buyer
    # two step filter to get the highest price at earliest time up on top.
    decorated = [(o.price, -o.time, -o.partner_id, o) for o in L]
    decorated.sort(reverse=True)
    undecorated = [o for price, time, partner_id, o in decorated]
    assert undecorated == [o3, o1, o2, o4]

    s = Seller(name=1)
    s.opportunities = L.copy()
    s.sort_opportunities()
    assert s.opportunities == [o3, o1, o2, o4], "Highest price, received at the earliest time is good. This wasn't..."

    b = Buyer(name=2, max_price=7)
    b.opportunities = L.copy()
    b.sort_opportunities()
    assert b.opportunities == [o4, o1, o2, o3], "sorting should have produced this result..."
    # now we know that the agents behave the same way as the sorting algorithm intended.


def test02():
    """ test that the AgentFactory produces agents."""
    f = AgentFactory()
    msg = MakeAgent(sender=44, receiver=AgentFactory.__name__, agent_to_be_created=AgentFactory)
    f.inbox.append(msg)
    f.update()
    agent_msg = f.outbox.popleft()
    agent = agent_msg.agent
    assert isinstance(agent, AgentFactory), \
        "we should have a second agent factory that was created by the first agent factory."


def demo(sellers=[], buyers=[], time_limit=True):
    """
    This demo() function was the first piece of code written in this
    python script. The simplicity of the demo forced the development
    process to target a linear execution model.
    """
    s = Scheduler(number_of_multi_processors=0)
    a = AgentFactory()
    b = BidDatabase(sellers=sellers, buyers=buyers)
    for agent in [a,b]:
        s.add(agent)
    if time_limit:
        s.run(seconds=1)
    else:
        s.run(pause_if_idle=True)

    contracts = {}
    for agent in s.agents:
        if isinstance(agent, (Buyer, Seller)):
            if agent.in_contract_with is None:
                contracts[(agent.__class__.__name__, agent.name)] = (None, None)
            else:
                agent2 = s.mailman.agent_register[agent.in_contract_with]
                contracts[(agent.__class__.__name__, agent.name)] = (agent2.__class__.__name__, agent2.name)

    print("Contracts at end:")
    for k,v in contracts.items():
        print("{}: {}".format(k,v), flush=True)
    assert len(contracts) > 0, "no contracts? That can't be true"
    return contracts


def test03():
    sellers = [5, 6, 7]
    s = Seller.__name__
    buyers = [1]  # result: 1 enters contract with 5 who has price 281.8 (the lowest price)
    b = Buyer.__name__
    results = demo(sellers, buyers, time_limit=False)
    expected_results={(b,1):(s,5), (s,5):(b,1), (s,6):(None,None), (s,7):(None,None)}
    for k,v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k,v)


def test04():
    sellers = [0]  # result: 0 enters contract with price 334.97 (the highest price)
    s = Seller.__name__
    buyers = [1, 2, 3]
    b = Buyer.__name__
    results = demo(sellers, buyers, time_limit=False)
    expected_results = {(s,0): (b,1), (b,1): (s,0), (b,2): (None,None), (b,3): (None,None)}
    for k, v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def test05():
    for i in range(3):
        sellers = [5, 6, 7]
        s = Seller.__name__
        buyers = [1, 2, 3]
        b = Buyer.__name__
        results = demo(sellers, buyers)
        expected_results = {(b,1): (s,7), (b,2): (s,6), (b,3): (s,5),
                            (s,5): (b,3), (s,6): (b,2), (s,7): (b,1)}
        for k, v in results.items():
            assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def test06():
    s, b = Seller.__name__, Buyer.__name__
    results = demo(sellers=[], buyers=[])
    expected_results = {(b, 0): (s, 4),
                        (b, 1): (s, 9),
                        (b, 2): (s, 7),
                        (b, 3): (s, 8),
                        (b, 4): (s, 10),
                        (b, 5): (s, 2),
                        (b, 6): (s, 5),
                        (b, 7): (s, 1),
                        (b, 8): (s, 0),
                        (b, 9): (s, 6),
                        (b, 10): (None, None),
                        (b, 11): (None, None),
                        (b, 12): (None, None),
                        (s, 0): (b, 8),
                        (s, 1): (b, 7),
                        (s, 2): (b, 5),
                        (s, 3): (None, None),
                        (s, 4): (b, 0),
                        (s, 5): (b, 6),
                        (s, 6): (b, 9),
                        (s, 7): (b, 2),
                        (s, 8): (b, 3),
                        (s, 9): (b, 1),
                        (s, 10): (b, 4),
                        }
    for k, v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def do_all():
    for k, v in sorted(globals().items()):
        if k.startswith("test") and callable(v):
            v()

if __name__ == "__main__":
    testing = False
    testing = True  # switch with CTRL+/ to run the demo.
    if testing:
        logging.basicConfig(level=logging.DEBUG)
        logging.info('Started')
        do_all()
        logging.info('Finished')
    else:
        demo(time_limit=False)

