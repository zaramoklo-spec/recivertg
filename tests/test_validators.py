"""تست‌های اعتبارسنجی"""
import pytest
from src.utils.validators import validate_phone_number, validate_code

def test_validate_phone_number():
    """تست اعتبارسنجی شماره تلفن"""
    assert validate_phone_number("+989123456789") == True
    assert validate_phone_number("989123456789") == True
    assert validate_phone_number("+1234567890") == True
    assert validate_phone_number("invalid") == False
    assert validate_phone_number("") == False

def test_validate_code():
    """تست اعتبارسنجی کد تایید"""
    assert validate_code("12345") == True
    assert validate_code("00000") == True
    assert validate_code("1234") == False
    assert validate_code("123456") == False
    assert validate_code("abcde") == False
