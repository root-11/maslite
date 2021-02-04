[![Build Status](https://travis-ci.com/root-11/maslite.svg?branch=master)](https://travis-ci.com/root-11/maslite)
[![Code coverage](https://codecov.io/gh/root-11/maslite/branch/master/graph/badge.svg)](https://codecov.io/gh/root-11/maslite)
[![Downloads](https://pepy.tech/badge/maslite)](https://pepy.tech/project/maslite)
[![Downloads](https://pepy.tech/badge/maslite/month)](https://pepy.tech/project/maslite/month)


# MASlite
A multi-agent platform contrived by [Bjorn Madsen](https://uk.linkedin.com/in/bmadsen)

All right reserved &copy; 2016-2021. MIT-license. 
All code has been written by the author in isolation and any similarity 
to other systems is purely coincidental. 

--------------

**New in version 2021.2.2+**

- dropping support for python 3.5. 

- subscribe now permits topic and agent id to limit the messages received.

- copy does no longer use deepcopy and will raise if you don't have a copy method!  
  Let me emphasise: All messages must have a `copy()` method.

- The `Scheduler` class must be initiated with one of two modes: real-time and simulated time.
  - real-time uses the clock / time.time() **(default)**
  - simulated time uses a jumping clock. 

- `Agent.set_alarm(..., relative=True, ....)`   
  defaults to True as most use cases use the alarm as "check again in x seconds"
  
- `Agent.list_alarms(receiver=None)`
  returns a list of (time, alarm message) set for the receiver.
  > Allows, for example, an agent A to read whether an alarm has been set for agent B, and
  > thereby refrain from setting an additional alarm.

- broadcasts are subscription based. To have broadcast-like methods, each agent must subscribe first.
  By default agents subscribe to their uuid and class name. But beware: 
  
  > Some users have been surprised that the broadcasting method could overflow their memory usage, so this is a safeguard. 
  In the auction demo, 1000 sellers sending 1 offer to each of 1000 buyers which generates 1,000,000 messages. 
  Instead of keeping a pool of 1,000,000 messages, where most are irrelevant, the new subscribe system, encourages 
  that the developer actively add and remove subscriptions, for example by subscribing to NewSeller announcements, 
  and afterwards only subscribe to specific agents that have offered prices within budget (or some other criteria).


--------------

#### MASlite explained in 60 seconds:

MASlite is a simle python module for creating multi-agent simulations.

- _Simple_ API: Only 3 modules to learn: Scheduler, Agent & Agent message
- _Fast_: Handles up to 270 million messages per second
- _Lightweight_: 52kB.

It only has 3 components:

- The scheduler (main loop)
  - handles pause and proceed with a single call.
  - assures repeatability in execution, which makes agents easy to debug.
  - handles up to 270 million messages per second.

- Agent's 

  - are python classes that have setup(), update() and teardown() methods that can be customized. 
  - can exchange messages using send() and receive().
  - can subscribe/unsubscribe to message classes.
  - have clocks and can set alarms.
  - can be tested individually.
  - can have independent I/O/Database interaction.
  
- Messages
  - that have sender and receiver enable direct communication
  - that have topics and no receiver are treated as broadcasts, and sent to subscribers.
  
The are plenty of use-cases for MASlite:

- Prototyping MASSIVE&trade; type games.
- Creating data processing pipeline
- Optimisation Engine, for:
  - Scheduling (using Bjorn Madsen's distributed scheduling method)
  - Auctions (using Dimtry Bertsekas alternating iterative auction)
 
-------------------

All the user needs to worry about are the protocols of interaction, 
which conveniently may be summarised as:

1. Design the messages that an agent will send or receive as regular 
python objects that inherit the necessary implementation details from 
a basic `AgentMessage`. The messages must have an unambiguous `topic`.
2. Write the functions that are supposed to execute once an agent 
 receives one of the messages.
3. Update the agents operations (`self.operations`) with a dictionary
that describes the relationship between `topic` and `function`.
4. Write the update function that maintains the inner state of the agent
using `send` to send messages, and using `receive` to get messages.

The user can thereby create an agent using just:

    class HelloMessage(AgentMessage):
        def __init__(self, sender, receiver)
            super().__init__(sender=sender, receiver=receiver)
    
    
    class myAgent(Agent):
        def __init__(self):
            super().__init__()
            self.operations[HelloMessage.__name__] = self.hello
        
        def update(self):
            while self.messages:
                msg = self.receive()
                operation = self.operations.get(msg.topic))
                if operation is not None:
                    operation(msg)
                else:
                    self.logger.debug("%s: don't know what to do with: %s" % (self.uuid), str(msg)))
                    
        def hello(self, msg)
            print(msg)


That simple!

The dictionary `self.operations` which is inherited from the `Agent`-class
is updated with `HelloMessage.__name__` pointing to the function `self.hello`. 
`self.operations` thereby acts 
as a pointer for when a `HelloMessage` arrives, so when the agents 
update function is called, it will get the topic from the message's and 
point to the function `self.hello`, where `self.hello` in this simple
example just prints the content of the message. 

More nuanced behaviour, can also be embedded without the user having
to worry about any externals. For example if some messages take 
precedence over others (priority messages), the inbox should be emptied 
in the beginning of the update function for sorting. 

Here is an example where some topics are treated with priority over 
others:

    class AgentWithPriorityInbox(Agent):
        def __init__(self):
            super().__init__()
            self.operations.update({"1": self.some_priority_function, 
                                    "2": self.some_function, 
                                    "3": self.some_function,  # Same function for 2 topics.! 
                                    "hello": self.hello, })
            self.priority_topics = ["1","2","3"]
            self.priority_messages = deque()  # from collections import deque
            self.normal_messages = deque()    # deques append and popleft are threadsafe.
    
        def update(self):
            # 1. Empty the inbox and sort the messages using the topic:
            while self.messages:
                msg = self.receive()
                if msg.topic in self.priority_topics:
                    self.priority_messages.append(msg)
                else:
                    self.normal_messages.append(msg)
            
            # 2. We've now sorted the incoming messages and can now extend
            # the priority message deque with the normal messages:
            self.priority_messages.extend(normal_messages)
            
            # 3. Next we process them as usual:
            while self.priority_messages:
                msg = self.priority_messages.popleft()
                operation = self.operations.get(msg.topic)
                if operation is not None:
                    operation(msg)
                else:
                    ...

The only thing which the user needs to worry about, is that the update
function cannot depend on any externals. The agent is confined to
sending (`self.send(msg)`) and receiving (`msg = self.receive()`) 
messages which must be processed within the function `self.update`.
Any responses to sent messages will not happen until the agent runs
update again.

If any state needs to be stored within the agent, such as for example
memory of messages sent or received, then the agents `__init__` should
declare the variables as class variables and store the information.
Calls to databases, files, etc. can of course happen, including the usage
of `self.setup()` and `self.teardown()` which are called when the agent
is, respectively, started or stopped. See the boiler-plate (below) for a more 
detailed description. 
 
### Boilerplate

The following boiler-plate allows the user to manage the whole lifecycle
of an agent, including:

1. add variables to `__init__` which can store information between updates.
2. react to topics by extending `self.operations`
2. extend `setup` and `teardown` for start and end of the agents lifecycle.
4. use `update` with actions before(1), during(2) and after(3) reading messages.

There are no requirements, for using all functions. The boiler-plate merely
seeks to illustrate typical usage.

There are also no requirements for the agent to be programmed in procedural,
functional or object oriented manner. Doing that is completely up to the 
user of MASlite.

    class Example(Agent):
        def __init__(self, db_connection):
            super().__init__()
            # add variables here.
            self._is_setup = False
            self.db_connection = db_connection
            
            # remember to register topics and their functions:
            self.operations.update({"topic x": self.x,
                                    "topic y": self.y,
                                    "topic ...": self....})
            
        def update(self):
            assert self._is_setup

            # do something before reading messages
            self.action_before_processing_messages()
        
            # read the messages
            while self.messages:
                msg = self.receive()
                
                # react immediately to some messages:
                operation = self.operations.get(msg.topic)
                if operation is not None:
                    operation(msg)
            
            # react after reading all messages:
            self.action_after_processing_all_messages()
        
        # Functions added by the user that are not inherited from the 
        # `Agent`-class. If the `update` function should react on these,
        # the topic of the message must be in the self.operations dict.
        
        def setup(self):
            self._is_setup = True
            # add own setup operations here.
            self.subscribe(self.__class__.__name__)
        
        def action_before_processing_messages(self)
            # do something.
            
        def action_after_processing_all_messages(self)
            # do something. Perhaps send a message to somebody that update is done?
            msg = DoneMessages(sender=self, receiver=SomeOtherAgent)
            self.send(msg)
        
        def x(msg):
            # read msg and send a response
            from_ = msg.sender
            response = SomeMessage(sender=self, receiver=from_) 
            self.send(response)
        
        def y(msg):
            with db_connection as db.:
                db.somefield.update(time.time())
                                
        def teardown(self):
            # add own teardown operations here.
            self.db_connection.close()
        

### Messages

Messages are objects and are required to use the base class `AgentMessage`.

When agents receive messages they should be interpreted by their topic, which
should (by convention) also be the class name of the message. Practice has shown
that there are no obvious reasons where this convention shouldn't apply, so 
messages which don't have a topic declared explicitly inherit the class name. 
An example is shown below:

    >>> from maslite import AgentMessage
    >>> class MyMsg(AgentMessage):
    ...     def __init__(sender, receiver):
    ...         super().__init__(sender=sender, receiver=receiver)
    ...
    
    >>> m = MyMsg(sender=1, receiver=2)
    >>> m.topic
    
    'MyMsg'

Adding functions to messages. Below is an example of a message with it's own
function(s): 

    class DatabaseUpdateMessage(AgentMessage):
        """ Description of the message """
        def __init__(self, sender, senders_db_alias):
            super().__init__(sender=sender, receiver=DatabaseAgent.__name__)
            self.senders_db_alias
            self._states = {1: 'new', 2: 'read'} 
            self._state = 1
            
        def get_senders_alias(self):
            return self.senders_db_alias
            
        def __next__(self)
            if self._state + 1 <= max(self._states.keys()):
                self._state += 1
        
        def state(self):
            return self._states[self._state]

The class `DatabaseUpdateMessage` is subclassed from the `AgentMessage` so that 
the basic message handling properties are available for the DatabaseUpdateMessage. 
This helps the user as s/he doesn't need to know anything about how the message 
handling system works.

The init function requires a sender, which normally defaults to the agent's `self`.
The `AgentMessage` knows that if it gets an agent in it's `__init__` call, it will
obtain the agents UUID and use that. Similar applies to a receiver, where the typical
operation is based on that the local agent gets a message from the sender and only 
knows the sender based on msg.get_sender() which returns the sending agents UUID. 
If the sender might change UUID, in the course of multiple runs, the local agent 
should be instructed to use, for example, the `senders_db_alias`. For the purpose
of illustration, the message above contains the function `get_senders_alias` which
then can be persistent over multiple runs.

The message is also designed to be returned to save pythons garbage collector:
When the DatabaseAgent receives the message, the `__next__`-function allows the
agent to call `next(msg)` to progress it's `self._state` from '1' (new) to '2' (read)
before returning it to the sender using 'self.send(msg)'. In such case it is 
important that the DatabaseAgent doesn't store the message in its variables, as
the message must __not__ have any open object pointers when sent. This is due to
multiprocessing which uses `multiprocessing.queue`s for exchanging messages, which
require that `Agent`s and `AgentMessage`s can be pickled.

If an `Agent` can't be pickled when added to the `Scheduler`, the scheduler will
raise an error explaining that the are open pointer references. Messages are a 
bit more tolerant as the `mailman` that manages the messages will try to send
the message and hope that the shared pointer will not cause conflicts. If sharing
of object pointers is required by the user (for example during prototyping) the 
scheduler must be set up with `number_of_multiprocessors=0` which forces the 
scheduler to run single-process-single-threaded. 


__Message Conventions__:

* Messages which have `None` as receiver are considered broadcasts. The logic is 
that if you don't know who exactly you are sending it to, send it it to `None`, and
you might get a response if any other agent react on the topic of the message.
The magic behind the scenes is handled by the schedulers mail manager 
which keeps track of all topics that any `Agent` subscribes to.
By convention the topic of the message should be `self.__class__.__name__`.

* Messages which have a `class.__name__` as receiver, will be received by all agents
of that class. This is configured when the agent is added to the scheduler in `s.add(agent)` 

* Messages which have a particular UUID as receiver, will be received by the agent 
holding that UUID. If anyone other agent is tracking that UUID, by subscribing to
it, then the tracking agent will receive a `deepcopy` of the message, and not the 
original. If the message has a `copy` method, this will be used instead of deepcopy. 

* To get the UUID of the sender the method `msg.sender` is available.

* To subscribe/unsubscribe during runtime the agents should use the `subscribe`
function directly.


### How to load data from a database connection 

When agents are added to the scheduler `setup` is run.
When agents are removed from `teardown` is run.

if agents are added and removed iteratively, they should load their 
state during `setup` and store it during `teardown` from some database. 
It is not necessary to let the scheduler know where the database is. 
The agents can keep track of this themselves. 

Though the user might find it attractive to use `uuid` to identify, a particular 
`Agent` the user should set the `uuid` in `super().__init__(uuid="this")`, as a the
`uuid` otherwise will be given be the scheduler.

### Getting started

To get started only 3 steps are required:

Step 1. setup a scheduler

    >>> from maslite import Agent, Scheduler
    >>> s = Scheduler()
    
Step 2. create agents which have an `update` method and (optionally)
a `setup` and `teardown`.

    >>> class MyAgent(Agent):
    ...     def __init__(self):
    ...         super().__init__()
    ...     def setup(self):
    ...         pass
    ...     def teardown(self):
    ...         pass
    ...     def update(self):
    ...         pass
        
    >>> m = MyAgent()
    >>> s.add(m)

Step 3. run the scheduler (nothing happens here)

    >>> s.run(pause_if_idle=True)

Other methods such as `s.run(seconds=None, iterations=None, 
pause_if_idle=False)` can be applied as the user finds it suitable.

Step 4. to stop the scheduler there are the following options:

1. Let it run until idle (most common)
2. Run for N seconds (suitable for real-time systems), 
3. Run for N iterations (suitable for interrupt checking)

Then leave the scheduler (and all the agents) in their set state, for
example to read the state of particular agents; and finally 
execute the `teardown` method, on all agents in a loop:

    >>> for uid, agent in s.agents.items():
    ...     agent.teardown()


### Debugging with pdb or breakpoints (PyCharm)

Debugging is easily performed by putting breakpoint at the beginning of
the update function. In that way you can watch what happens inside the 
agent during its state-update.

### Typical mistakes

The user constructs the agent correctly with:
 
1. the methods `update`, `send`, `receive`, `setup` and `teardown`,
2. adding the agent to the scheduler using `scheduler.add(agent)`.
3. runs the scheduler using `scheduler.run()`, 

...but... 

Q: The agents don't seem to update?

A: The agents are not getting any messages and are therefore not updated.
This is correct behaviour, as `update` only should run when there are
new messages! 
To force agents to run `update` in every scheduling cycle, use the hidden 
method: `agent.keep_awake=True`. Doing this blindly however is a poor design
choice if the agent merely is polling for data. For this purpose 
`agent.set_alarm_clock(agent.now()+1)` should be used, as this allows the
agent to sleep for 1 second and the be "woken up" by the alarm message.

The reason it is recommended to use the alarm instead of setting 
`keep_awake=True` is that the workload of the system remains transparent 
at the level of message exchange. Remember that the internal state of 
the agents should always be hidden whilst the  messages should be 
indicative of any activity. 

...

