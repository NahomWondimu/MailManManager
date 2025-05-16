class Email:
    # Attributes
    def __init__(self, header, subject, message):
        self.header = header
        self.subject = subject
        self.message = message

    @classmethod
    def toString(cls):
        return cls.header, cls.subject, cls.message