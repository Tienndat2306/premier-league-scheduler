class Stadium:
    def __init__(self, id: int, name: str, city: str):
        self.id = id
        self.name = name
        self.city = city

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "city": self.city
        }

    def __repr__(self):
        return f"{self.name} ({self.city})"
