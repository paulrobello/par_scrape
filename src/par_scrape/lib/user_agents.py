"""Generate a random user agent."""

import random


def get_random_user_agent() -> str:
    """Generate a random user agent."""
    os_list = ["Windows NT 10.0", "Macintosh; Intel Mac OS X 10_15_7", "Macintosh; Intel Mac OS X 10_13_2"]
    browser_list = ["Chrome", "Firefox", "Safari", "Edge"]
    webkit_version = f"{random.randint(601, 620)}.{random.randint(1, 36)}.{random.randint(1, 15)}"
    chrome_version = f"{random.randint(100, 131)}.0.{random.randint(1000, 5000)}.{random.randint(1, 200)}"
    edge_version = f"{random.randint(110, 120)}.0.{random.randint(1000, 2000)}.{random.randint(1, 100)}"
    firefox_version = f"{random.randint(130, 133)}.{random.randint(0, 9)}"
    os = random.choice(os_list)
    browser = random.choice(browser_list)

    if "Windows" in os:
        platform = "Win64; x64"
    else:
        platform = os.split("; ")[1]

    webkit = f" AppleWebKit / {webkit_version}"
    gecko = " (KHTML, like Gecko)"
    if browser == "Safari":
        version = f"Version/{random.randint(14, 18)}.{random.randint(0, 3)} Safari/{webkit_version}"
    elif browser == "Firefox":
        version = f"Gecko/20100101 Firefox/{firefox_version}"
        gecko = ""
        webkit = ""
    elif browser == "Edge":
        version = f"Edg/{edge_version}"
    else:  # Chrome
        version = f"Chrome/{chrome_version} Safari/{webkit_version}"

    return f"Mozilla/5.0 ({os.split('; ')[0]}; {platform}){webkit}{gecko} {version}"


if __name__ == "__main__":
    print(get_random_user_agent())
