"""Temperature conversion utilities."""

def fahrenheit_to_celsius(temp_f: float) -> float:
    """Convert temperature from Fahrenheit to Celsius.

    Args:
        temp_f: Temperature in Fahrenheit

    Returns:
        Temperature in Celsius
    """
    return (temp_f - 32) * 5 / 9


def celsius_to_fahrenheit(temp_c: float) -> float:
    """Convert temperature from Celsius to Fahrenheit.

    Args:
        temp_c: Temperature in Celsius

    Returns:
        Temperature in Fahrenheit
    """
    return (temp_c * 9 / 5) + 32
