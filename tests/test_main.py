import pytest

from main import greet


def test_greet_with_valid_name() -> None:
    """正常系: 通常の文字列を渡すと、挨拶文が返る。"""
    # Arrange
    name = "Alice"

    # Act
    result = greet(name)

    # Assert
    assert result == "Hello, Alice!"


def test_greet_strips_surrounding_whitespace() -> None:
    """正常系: 前後の空白は除去されて返る。"""
    # Arrange
    name = "  Alice  "

    # Act
    result = greet(name)

    # Assert
    assert result == "Hello, Alice!"


def test_greet_with_empty_string() -> None:
    """準正常系: 空文字は想定内のエラーになる。"""
    # Arrange
    name = ""

    # Act & Assert
    with pytest.raises(ValueError, match="name must not be empty"):
        greet(name)


def test_greet_with_whitespace_only() -> None:
    """準正常系: 空白のみの文字列も想定内のエラーになる。"""
    # Arrange
    name = "   "

    # Act & Assert
    with pytest.raises(ValueError, match="name must not be empty"):
        greet(name)


def test_greet_with_pure_digit_string() -> None:
    """準正常系: 数字だけの文字列は想定内のエラーになる。"""
    # Arrange
    name = "123"

    # Act & Assert
    with pytest.raises(ValueError, match="name must not contain digits"):
        greet(name)


def test_greet_with_digit_mixed_in_name() -> None:
    """準正常系: 数字を含む文字列も想定内のエラーになる。"""
    # Arrange
    name = "Alice1"

    # Act & Assert
    with pytest.raises(ValueError, match="name must not contain digits"):
        greet(name)


def test_greet_with_none() -> None:
    """異常系: Noneは想定外の型なのでエラーになる。"""
    # Arrange
    name = None

    # Act & Assert
    with pytest.raises(AttributeError):
        greet(name)


def test_greet_with_int_type() -> None:
    """異常系: intは想定外の型なのでエラーになる。"""
    # Arrange
    name = 123

    # Act & Assert
    with pytest.raises(AttributeError):
        greet(name)
