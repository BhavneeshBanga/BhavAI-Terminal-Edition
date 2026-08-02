# test_clipboard.py
from PIL import ImageGrab
import pyperclip

print("ImageGrab result:", ImageGrab.grabclipboard())
print("pyperclip result:", pyperclip.paste())