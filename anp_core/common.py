# This module contains shared classes and functions to avoid circular imports.

class Msg:
    def __init__(self, sender, targeter, content):
        self.sender = sender
        self.targeter = targeter
        self.content = content