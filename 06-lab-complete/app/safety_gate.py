"""
Safety gate runs BEFORE the AI classifier.
Three checks (in order):
1. is_crisis()        — self-harm / suicide intent → hard refuse, show crisis resources
2. is_high_risk()     — medical risk keywords → force advisory route
3. is_injection()     — off-topic instructions embedded in message → block and warn
"""

CRISIS_KEYWORDS = [
    # Suicide intent
    "tự tử", "tự sát", "muốn chết", "tìm cách chết", "kết thúc cuộc sống",
    "không muốn sống", "chán sống",
    # Drug-mediated self-harm
    "uống thuốc để chết", "uống thuốc để tự tử", "uống thuốc tự tử",
    "dùng thuốc để chết", "liều chết", "liều gây chết", "liều tử vong",
    "bao nhiêu viên để chết", "uống bao nhiêu để chết",
    # English equivalents (in case of code-switching)
    "want to die", "kill myself", "end my life", "overdose to die",
]

HIGH_RISK_KEYWORDS = [
    # Chronic disease context
    "tiểu đường", "đái tháo đường", "huyết áp", "tim mạch", "suy tim",
    "suy thận", "suy gan", "ung thư", "động kinh", "parkinson",
    # Drug interaction signals
    "đang uống thuốc", "đang dùng thuốc", "đang điều trị",
    "tương tác thuốc", "kết hợp thuốc", "uống cùng lúc",
    # Vulnerable populations
    "mang thai", "thai kỳ", "cho con bú", "trẻ sơ sinh", "trẻ em dưới",
    # Dose escalation signals
    "liều cao", "tăng liều", "quá liều", "uống nhiều hơn",
    # Allergy / adverse event
    "dị ứng thuốc", "phản ứng thuốc", "tác dụng phụ nghiêm trọng",
    # Explicit advisory request
    "bệnh mãn tính", "bệnh nền",
]

# Patterns that signal off-topic instructions injected into the message.
INJECTION_PATTERNS = [
    # Code generation requests
    "viết code", "write code", "viết python", "write python",
    "viết script", "tạo code", "generate code", "lập trình",
    # Role / persona hijack
    "bạn là", "you are", "pretend", "act as", "đóng vai",
    "ignore previous", "bỏ qua hướng dẫn", "quên hướng dẫn",
    "forget your instructions", "new instructions",
    # Prompt leak attempts
    "system prompt", "show prompt", "repeat your instructions",
    "lặp lại prompt", "in ra prompt",
    # Translation / summarise unrelated content
    "dịch đoạn", "tóm tắt đoạn", "summarize the following",
    # General off-topic task injection
    "hãy làm", "hãy thực hiện", "execute the following",
]


def is_crisis(message: str) -> bool:
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in CRISIS_KEYWORDS)


def is_high_risk(message: str) -> bool:
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in HIGH_RISK_KEYWORDS)


def is_injection(message: str) -> bool:
    msg_lower = message.lower()
    return any(pattern in msg_lower for pattern in INJECTION_PATTERNS)
