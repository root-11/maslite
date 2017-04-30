from outscale.core import Agent, LogMessage


class TestAgent(Agent):
    def __init__(self):
        super().__init__()

    def setup(self):
        print("TestAgent running 'setup'")
        pass

    def update(self):
        print("TestAgent running 'update'")
        while self.messages:
            msg = self.receive()
            operation = self.operations.get(msg.topic)
            if operation is not None:
                operation(msg)
            else:
                self.logger("%s: don't know what to do with: %s" % (self.uuid, str(msg)))

    def teardown(self):
        print("TestAgent running 'teardown'")
        pass


class WorkIntensiveAgent(Agent):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.total_updates = 0
        self.inbox.append('placeholder that is neither consumed nor used '
                          'and therefore triggers automatic update of the agent')

    def setup(self):
        pass

    def teardown(self):
        pass

    def update(self):
        workload = 1000000
        log = False
        j = 0
        for i in range(workload):
            j += i
        if log:
            msg = LogMessage(sender=self, receiver=None, log_level="DEBUG",
                             log_message="Updating {}-{}: Update no: {}".format(
                                 self.__class__.__name__, self.name, self.total_updates))
            self.send(msg)
        self.total_updates += 1
