class CommandRegex:
    DONE = r"\/done\b"
    CANCEL = r"/cancel\b"
    DONE_OR_CANCEL = r"/(?:done|cancel)\b"


class Commands:
    STANDARD_CANCEL_COMMANDS = ['cancel', 'c', 'done', 'd']

