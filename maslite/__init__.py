from maslite.core import Agent, AgentMessage, Scheduler, Sentinel
from maslite.core import AlarmMessage, PauseMessage
from maslite.core import SetTimeAndClockSpeedMessage, StartMessage, StopMessage
from maslite.core import SubscribeMessage, UnSubscribeMessage, GetSubscribersMessage
from maslite.core import GetSubscriptionTopicsMessage, Clock
from maslite.core import AddNewAgent, RemoveAgent

"""

Maslite is a multi-agent platform contrived by Bjorn Madsen and is
in public domain as a MIT License, which allows anyone to do
whatever they want. See the license for details.

From Wikipedia:

A multi-agent system (M.A.S.) is a computerized system composed of multiple
interacting intelligent agents within an environment. Multi-agent systems
can be used to solve problems that are difficult or impossible for an
individual agent or a monolithic system to solve. Intelligence may include
some methodic, functional, procedural approach, algorithmic search or
reinforcement learning. Although there is considerable overlap, a multi-agent
system is not always the same as an agent-based model (ABM). The goal of an
ABM is to search for explanatory insight into the collective behavior of
agents (which don't necessarily need to be "intelligent") obeying simple
rules, typically in natural systems, rather than in solving specific practical
or engineering problems. The terminology of ABM tends to be used more often
in the sciences, and MAS in engineering and technology.
[https://en.wikipedia.org/wiki/Multi-agent_system]

How to use
===========

See readme.md

Examples
========

See maslite_demos

"""

__author__ = ['bjorn.madsen@operationsresearchgroup.com']
__version__ = '2017.10'
__copyright__ = '2016,2017'
__license__ = 'MIT License'
