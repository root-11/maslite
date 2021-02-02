from demos.scheduling import Machine, Order, StockAgent, Job
from maslite import Scheduler


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