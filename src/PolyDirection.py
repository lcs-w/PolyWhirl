import enum


class PolyDirection(enum.Enum):
    YES = True
    NO = False

    def __str__(self):
        return self.name.lower().capitalize()

    def __bool__(self):
        return self.value


if __name__ == "__main__":
    direction = PolyDirection.YES
    print(direction)
    print(bool(direction))
    print(int(bool(direction)))
