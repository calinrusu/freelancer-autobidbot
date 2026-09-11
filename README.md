# Python autobidding bot for freelancer.com projects

A python3 script for logging in to the freelancer.com freelancer account, scraping for project matching certain skills, budget and type and placing automatic bids with a predefined bid text, average budget and default timeline (as in the bid form)

# Requirements

- Python 3
- Selenium web driver for Chrome

# Configuration

- Please edit in the autobid.py file the lines 12 to 28 to set the correct set of skills, projects limit, type and your bid text.
- To set your username and password we are not using plain values in the script itself but setting them instead in the python console. We set them as environment varibales. To do so:
>>> import os
>>> os.environ['FREELANCER_EMAIL'] = 'youremailaddress'
>>> os.environ['FREELANCER_USERNAME'] = 'yourusername'
>>> os.environ['FREELANCER_PASSWORD'] = 'yourpassword'
>>> quit()

# Running

- cd into the directory where you have autobid.py and /path/to/python3 autobid.py
