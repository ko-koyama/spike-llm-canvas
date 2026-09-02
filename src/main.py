def greet(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValueError("name must not be empty")
    if any(char.isdigit() for char in stripped):
        raise ValueError("name must not contain digits")
    return f"Hello, {stripped}!"


if __name__ == "__main__":
    print(greet("World"))
