from maslite import Agent, AgentMessage, Scheduler
from collections import namedtuple

__description__ = """The scheduling demo presented in Bjorn Madsen's PhD thesis (https://goo.gl/YbHVzi).
"""


class Order(AgentMessage):
    def __init__(self, sender, receiver, order_items):
        """
        :param sender: Agent class or Agent uuid
        :param receiver: Agent class or Agent uuid
        :param order_items: A dictionary of SKUs & quantities, eg: {"A": 1, "B": 1,"C": 1, ...}
        :param wanted_sequence: optional if a wanted sequence is declared it should exhaust all the sku's
        """
        super().__init__(sender, receiver)
        self.order_items = order_items

    def get_ordered_items(self):
        return self.order_items


# I've created a nice light-weight object for storing the data in the supply schedule
SupplyLine = namedtuple('SupplyLine', ('time', 'sku', 'qty'))


class SupplySchedule(AgentMessage):
    def __init__(self, sender, receiver, schedule):
        """
        :param sender: Agent class or Agent uuid
        :param receiver: Agent class or Agent uuid
        :param schedule: list of items with [[time, sku, qty], [time, sku, qty], ... , [time, sku, qty]]
        eg: [[2, "A", 1],
             [2, "B", 3],
             ...
             [22, "G", 1]]
        """
        super().__init__(sender, receiver)
        for row in schedule:
            assert isinstance(row, SupplyLine)
        self.schedule = schedule

    def get_schedule(self):
        return self.schedule


class Job(object):
    def __init__(self, order_sku, resource_sku,
                 supply_time, run_time, idle_time, start_time, finish_time,
                 quantity, customer):
        self.order_sku = order_sku
        self.resource_sku = resource_sku
        self.supply_time = supply_time
        self.run_time = run_time
        self.idle_time = idle_time
        self.start_time = start_time
        self.finish_time = finish_time
        self.quantity = quantity
        self.customer = customer

    def __str__(self):
        names = [self.order_sku, self.resource_sku,
                 self.supply_time, self.run_time, self.idle_time, self.start_time, self.finish_time,
                 self.quantity]
        return "<{} {}>".format(self.__class__.__name__, " ".join([str(n) for n in names]))

    def __repr__(self):
        return self.__str__()


class JobsWithIdleTime(AgentMessage):
    def __init__(self, sender, receiver, jobs_with_idle_time):
        """
        A specialised message for communicating jobs with idletime.
        :param sender: Agent class or Agent uuid
        :param receiver: Agent class or Agent uuid
        :param current_supply_schedule: The current schedule in which jobs processed.
        :param jobs_with_idle_time: list of jobs with idle time
        """
        super().__init__(sender, receiver)
        self.jobs_with_idle_time = jobs_with_idle_time

    def get_jobs_with_idle_time(self):
        return self.jobs_with_idle_time


class Machine(Agent):
    def __init__(self, name, run_times, transformations):
        """
        :param run_times: run_times as a dictionary of skus & times in seconds
                          for example: {"A":14, "B":7,"C":3, "D": 6}
        :param transformations: dict of skus(in):skus(out) required for the machine to
                                create a sku(out) from a sku(in)
        """
        super().__init__()
        self.name = name
        self.transformations = transformations
        self.run_times = run_times
        self.customer = None
        self.supplier = None
        self.stock = {}
        self.jobs = []
        self.finish_time = -1
        self.operations.update({Order.__name__: self.process_order,  # new order arrives.
                                SupplySchedule.__name__: self.update_schedule_with_supply_schedule,
                                JobsWithIdleTime.__name__: self.deal_with_idle_time})  # supply schedule arrives.

    def __str__(self):
        return "<{} {}>".format(self.__class__.__name__, self.name)

    def setup(self):
        pass

    def teardown(self):
        pass

    def update(self):
        while self.messages:
            msg = self.receive()
            operation = self.operations.get(msg.topic, None)
            if operation is not None:
                operation(msg)

        self.update_finish_time()

    def set_customer(self, agent):
        assert isinstance(agent, Agent)
        self.customer = agent.uuid

    def set_supplier(self, agent):
        assert isinstance(agent, Agent)
        self.supplier = agent.uuid

    def update_finish_time(self):
        """
        This function updates the finish time as a KPI to show the user.
        """
        if self.jobs:
            last_job = self.jobs[-1]
            assert isinstance(last_job, Job)
            if last_job.finish_time:
                self.finish_time = last_job.finish_time

    def process_order(self, msg):
        """
        Process order registers any new order in the joblist.
        :param msg: Order class.
        """
        assert isinstance(msg, Order)
        ordered_items = msg.get_ordered_items()

        # we register the order as jobs:
        for sku, qty in ordered_items.items():
            job = Job(order_sku=sku,
                      resource_sku=self.transformations.get(sku, None),
                      supply_time=None,
                      run_time=self.run_times.get(sku, None),
                      idle_time=None,
                      start_time=None,
                      finish_time=None,
                      quantity=qty,
                      customer=msg.sender)
            self.jobs.append(job)

        # if it's a brand new schedule, then we'll have to update sort the jobs first.
        if any([j.supply_time is None for j in self.jobs]):
            self.schedule_jobs_using_shortest_run_time_first()
        # after registering the order we need the materials...
        self.order_materials()

    def order_materials(self):
        # below we transformation the order of {abcdefg} using the material {M1a, M1b, .... M1f}
        # so that a revised order can be sent to the supplier
        supplies_required = {}  # SKU: qty (following the order class)
        for job in self.jobs:
            supplies_required[job.resource_sku] = job.quantity
        else:
            pass

        assert self.supplier is not None, "supplier must be assigned before it can receive messages..!"
        new_order = Order(sender=self, receiver=self.supplier, order_items=supplies_required)
        self.send(new_order)

    def schedule_jobs_using_shortest_run_time_first(self):
        jobs = [(j.run_time, j.order_sku, j) for j in self.jobs]
        jobs.sort()
        self.jobs = [j for run_time, order_sku, j in jobs]

    def schedule_jobs_using_supply_time(self):
        jobs = [(j.supply_time, j.run_time, j) for j in self.jobs]
        jobs.sort()
        self.jobs = [j for supply_time, run_time, j in jobs]

    def update_schedule_with_supply_schedule(self, msg):
        """
        :param msg: SupplySchedule

        When we receive a SupplySchedule, we are getting an update to our jobs
        which we'll need to process.
        """
        assert isinstance(msg, SupplySchedule)
        supply_schedule = msg.get_schedule()

        for row in supply_schedule:
            assert isinstance(row, SupplyLine)
            for job in self.jobs:
                assert isinstance(job, Job)
                if row.sku == job.resource_sku:
                    job.supply_time = row.time
                else:
                    pass
        # now we'll need to sort the jobs as supplied.
        self.schedule_jobs_using_supply_time()

        # when we've received an updated supply schedule, we will need to update the jobs.
        self.update_jobs_table()

    def update_jobs_table(self):
        if any([j.supply_time is None for j in self.jobs]):
            # then we can't continue as we're waiting for supplies.
            return

        # else:
        previous_job = None
        for idx, job in enumerate(self.jobs):
            assert isinstance(job, Job)

            if previous_job is None:
                job.start_time = max(0, job.supply_time)
                job.idle_time = job.start_time
            else:
                job.start_time = max(previous_job.finish_time, job.supply_time)
                job.idle_time = job.start_time - previous_job.finish_time
            job.finish_time = job.start_time + job.run_time

            previous_job = job

        if any([j.supply_time is None for j in self.jobs]):
            # then we can't continue as we're waiting for supplies.
            return
        else:  # we have a complete schedule and can communicate any idle time to peers
            self.communicate_to_peers()

    def communicate_to_peers(self):
        jobs_with_idle_time = []
        total_idle_time = 0
        for idx, job in enumerate(self.jobs):
            if job.idle_time != 0:
                total_idle_time += job.idle_time
                jobs_with_idle_time.append(idx)

        # if there's a supplier, we'll send the idle time to it.
        if sum(jobs_with_idle_time) > 0:  # sum of jobs with idle time will be zero if only index zero is present.
            new_msg = JobsWithIdleTime(sender=self, receiver=self.supplier,
                                       jobs_with_idle_time=jobs_with_idle_time)  # and the index that's not good.
            self.send(new_msg)

        # if there's a customer, we'll send the new supply schedule to it.
        if self.customer and self.jobs:
            customer_supply_schedule = []
            for job in self.jobs:
                sl = SupplyLine(time=job.finish_time,
                                sku=job.order_sku,
                                qty=job.quantity)
                customer_supply_schedule.append(sl)
            new_msg = SupplySchedule(sender=self, receiver=self.customer, schedule=customer_supply_schedule)
            self.send(new_msg)

    def deal_with_idle_time(self, msg):
        assert isinstance(msg, JobsWithIdleTime)
        jobs_with_idle_time = msg.get_jobs_with_idle_time()
        while jobs_with_idle_time:
            index = jobs_with_idle_time.pop(0)
            if index == 0:
                pass  # can't move before index zero
            else:  # swap positions with the previous job.
                self.jobs[index - 1], self.jobs[index] = self.jobs[index], self.jobs[index - 1]
        # finally:
        self.update_jobs_table()


class StockAgent(Agent):
    def __init__(self, name=''):
        super().__init__()
        self.customer = None
        self.name = name
        self.operations.update({Order.__name__: self.process_order})

    def __str__(self):
        return "<{} {}>".format(self.__class__.__name__, self.name)

    def setup(self):
        pass

    def teardown(self):
        pass

    def update(self):
        while self.messages:
            msg = self.receive()
            operation = self.operations.get(msg.topic, None)
            if operation is not None:
                operation(msg)

    def set_customer(self, agent):
        assert isinstance(agent, Agent)
        self.customer = agent.uuid

    def process_order(self, msg):
        assert isinstance(msg, Order)
        ordered_items = msg.get_ordered_items()

        supplies = []
        for sku, qty in ordered_items.items():
            sl = SupplyLine(time=0,  # should really be self.now() to use the schedulers clock.
                            sku=sku,
                            qty=qty)
            supplies.append(sl)
        new_msg = SupplySchedule(sender=self, receiver=self.customer, schedule=supplies)
        self.send(new_msg)


def test01():
    s = Scheduler()
    # create M2
    m2_runtimes = {'A': 14, 'B': 7, 'C': 3, 'D': 10, 'E': 5, 'F': 6, 'G': 6}
    m2_transformations = {'A': 'M1A', 'B': 'M1B', 'C': 'M1C', 'D': 'M1D', 'E': 'M1E', 'F': 'M1F', 'G': 'M1G'}
    m2 = Machine(name='M2', run_times=m2_runtimes, transformations=m2_transformations)
    order = Order(sender=m2, receiver=m2,
                  order_items={"A": 1, "B": 1, "C": 1, "D": 1, "E": 1, "F": 1, "G": 1})  # {SKU:qty}
    m2.inbox.append(order)
    # create M1
    m1_runtimes = {'M1A': 2, 'M1B': 5, 'M1C': 10, 'M1D': 8, 'M1E': 4, 'M1F': 12, 'M1G': 9}
    m1_transformations = {'M1A': 'rawA', 'M1B': 'rawB', 'M1C': 'rawC', 'M1D': 'rawD',
                          'M1E': 'rawE', 'M1F': 'rawF', 'M1G': 'rawG'}
    m1 = Machine(name="M1", run_times=m1_runtimes, transformations=m1_transformations)

    # create Stock Agent.
    stock_agent = StockAgent()
    stock_agent.set_customer(m1)
    # Below we are setting the uuid that the agent (m1) needs to talk to (m2) and vice versa.
    m2.set_supplier(m1)
    m1.set_customer(m2)
    m1.set_supplier(stock_agent)

    # Add m1 and m2 to the scheduler.
    for agent in [m1, m2, stock_agent]:
        s.add(agent)
    s.run(pause_if_idle=True)

    check_sequence = ["A", "E", "B", "D", "G", "F", "C"]
    try:
        for idx, job in enumerate(m2.jobs):
            assert isinstance(job, Job)
            assert job.order_sku == check_sequence[idx]
    except AssertionError:
        raise AssertionError("Expected the final sequence as: {}\n but got: {}".format(check_sequence,
                                                                                       [job.order_sku for job in
                                                                                        m2.jobs]))

    s.stop()


if __name__ == "__main__":
    test01()
