import os

# Importing __main__ is part of the unit tests; never bootstrap /data there.
os.environ["BILIBILI_AUTO_CREATE_ENV"] = "false"
