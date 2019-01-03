#!/usr/bin/python3
from collections import defaultdict
from getpass import getpass
import configparser
import splinter
import smtplib
import code
import time
import os
import re


"""
Author: Terrence Plunkett
Auther Email: eightys3v3n@gmail.com

A script that checks for available spaces in classes via the Mount Royal website.
"""


HEADLESS = True


class ButtonNotFound(Exception): pass
class ConfigError(Exception): pass


class Course:
    def __init__(self, **kwargs):
        self.client_email = ''
        self.name    = ""
        self.number  = ''
        self.term    = ''
        self.subject = ''
        self.desired_sections = []

        for k, v in kwargs.items():
            setattr(self, k, v)

        if self.client_email == '':
            raise ValueError("Course must have a client email to notify")

        if self.name == "":
            raise ValueError("Course must have a name")

        if self.number == '':
            raise ValueError("Course must have a number")

        if self.term == '':
            raise ValueError("Course must have a term")

        if self.subject == '':
            raise ValueError("Course must have a subject")

        if len(self.desired_sections) == 0:
            raise ValueError("Course must have desired sections")
        if not all(isinstance(s, str) for s in self.desired_sections):
            raise ValueError("All desired sections must be strings")


    def __dict__(self):
        ret = {}
        ret['client_email'] = self.client_email
        ret['name']         = self.name
        ret['number']       = self.number
        ret['term']         = self.term
        ret['subject']      = self.subject
        ret['sections']     = self.desired_sections
        return ret


    def __str__(self):
        d = self.__dict__()
        s = ''
        for k, v in d.items():
            s += '{:<13}: {}\n'.format(k, v)
        s = s[0:-1]
        return s


    def __repr__(self):
        return self.__str__()


def click_button(name=None, value=None):
    global browser
    complete = False

    for i in range(10):
        try:
            if name is not None:
                button = browser.find_by_name(name)
            elif value is not None:
                button = browser.find_by_value(value)
        except TypeError:
            time.sleep(0.5)
            continue
        if button == []:
            raise ButtonNotFound(name)
        button.click()
        break
    else:
        raise Exception("Failed to complete for some weird repeat error")


def notify_email(msg, *, username, password, from_email, to_email):
    #print("msg: '{}'\nusername: '{}'\npassword: '{}'\nfrom_email: '{}'\nto_email: '{}'".format(msg, username, password, from_email, to_email))
    server = smtplib.SMTP('smtp.gmail.com', 587)
    r = server.ehlo()
    #print(r)
    r = server.starttls()
    #print(r)
    r = server.login(username, password)
    #print(r)
    r = server.sendmail(from_email, to_email, msg)
    #print(r)
    server.close()


def open_browser():
    global browser
    browser = splinter.Browser("chrome", headless=HEADLESS)
    browser.__enter__()


def nav_MyMRU():
    global browser
    browser.visit("https://mymru.ca")


def login_MyMRU(username, password):
    global browser
    browser.fill('username', username)
    browser.fill('password', password)
    click_button('submit')


def nav_course_list():
    global browser
    browser.visit('http://www.mru.ca/rp-look-up-courses')


def select_term(term):
    global browser
    browser.select('p_term', term)
    click_button(value='Submit')


def select_subject(subject):
    global browser
    browser.select('sel_subj', subject)
    click_button(value='Course Search')


def select_class(class_name, class_number):
    global browser
    classes = browser.find_by_tag('tr')
    while None in classes: classes.remove(None)
    for c in classes:
        if re.match('^\d+\s.*$', c.text) is None:
            classes.remove(c)
    for c in classes:
        if c.text == ' '.join([class_number, class_name]):
            c.click()
            break


def find_sections(subject, name, number):
    global browser
    all_sections = browser.find_by_tag('tr')
    all_sections = list(all_sections)
    _all_sections = []
    for s in all_sections:
        text = s.text
        text = text.split('\n')
        regex = '^.*\d{{5}}.*{} {}.*{}.*$'.format(subject, number, name)
        if re.match(regex, text[0]) is not None:
            _all_sections.append(s.text)
        elif text[0].endswith('Note:'):
            _all_sections[-1] += '\n'+s.text

#    for s in _all_sections:
#      print(s)

    all_sections = {}
    for i, s in enumerate(_all_sections):
        s = s.replace('\n', '|')

        # Match the class text and extract relevant information
        regex = '^(.*)(\d{{5}}) \w{{4}} \d{{4}} \d{{3}} .*{}.* (\d+) (\d+) (-?\d+) (\d+) .*'.format(name)
        match = re.match(regex, s)
        if match is None:
            raise Exception("Class didn't match regex\n{}".format(s))

        match = match.groups()
        status = match[0]
        number = match[1]
        max_size = int(match[2])
        accepted = int(match[3])
        remaining = int(match[4])
        waiting_list = int(match[5])
        all_sections[number] = {
            'raw': s,
            'status': status,
            'crn': number,
            'cap': max_size,
            'accepted': accepted,
            'remaining': remaining,
            'wait_list': waiting_list,
        }
    return all_sections


def trim_sections(all_sections, sections):
    trimmed_sections = {}
    for section in sections:
        if section not in all_sections:
            print("Couldn't find section '{}'".format(section))
        trimmed_sections[section] = all_sections[section]
    return trimmed_sections


def check_availability(desired_sections, sections):
    availability = {s:None for s in desired_sections}
    for s, i in sections.items():
        if s not in desired_sections:
            continue

        if i['remaining'] > 0:
            if i['wait_list'] > 0:
                print("Section {} has space available but it's reserved for the waitlist".format(s))
                availability[s] = "Available: Reserved for waitlist"
            elif 'RESTRICTION' in i['raw']:
                print("Section {} has space available but it has restrictions in place".format(s))
                availability[s] = "Available: Restrictions in place"
            else:
                print("Section {} has space available".format(s))
                availability[s] = "Available"
        else:
            print("Section {} has no spaces".format(s))
            availability[s] = "Not available"
    return availability


def notify_availability(email_info, courses):
    clients = defaultdict(str)
    for section, course in courses.items():
        if course['status'] == "Available":
            clients[course['info'].client_email] += "\n{}.{}({}) has space available".format(
                course['info'].subject, course['info'].number, section)
    for client, msg in clients.items():
        if msg != '':
            msg = msg[1:]
            notify_email(msg, **email_info, to_email=client)
            # used if the script host also wants a message when a client gets a message.
            # notify_email("{} -> {}".format(msg, client), **email_info, to_email='maintainer email')


def close():
    global browser
    browser.__exit__(None, None, None)


def check_courses(username, password, email_info, courses):
    print("{:60}".format("Launching browser..."), end='')
    open_browser()
    print("Done.")

    print("{:60}".format("Navigating to MyMRU..."), end='')
    nav_MyMRU()
    print("Done.")

    print("{:60}".format("Logging in..."), end='')
    login_MyMRU(username, password)
    print("Done.")

    for course in courses:
        print("{:60}".format("Navigating to course listings..."), end='')
        nav_course_list()
        print("Done.")

        print("{:60}".format("Selecting term..."), end='')
        select_term(course.term)
        print("Done.")

        print("{:60}".format("Selecting subject..."), end='')
        select_subject(course.subject)
        print("Done.")

        print("{:60}".format("Selecting class..."), end='')
        select_class(course.name, course.number)

        print("Done.")

        print("{:60}".format("Finding all sections..."), end='')
        all_sections = find_sections(course.subject, course.name, course.number)
        print("Done.")

        sections = trim_sections(all_sections, course.desired_sections)
        availabilities = check_availability(course.desired_sections, sections)
        availabilities = {k: {'status': v, 'info': course} for k, v in availabilities.items()}
        notify_availability(email_info, availabilities)
    close()


def read_config(path):
    config = configparser.ConfigParser()
    config.read(path)
    parsed_config = defaultdict(None)

    if 'check_interval' in config['General']:
        parsed_config['check_interval'] = int(config['General']['check_interval'])
        parsed_config['check_interval'] = max(10, parsed_config['check_interval'])

    # MyMRU username and password. Parse or prompt.
    if 'username' in config['MyMRU']:
        parsed_config['username'] = config['MyMRU']['username']
        if 'password' in config['MyMRU']:
            parsed_config['password'] = config['MyMRU']['password']
        else:
            parsed_config['password'] = getpass('MyMRU password: ')
    else:
        parsed_config['username'] = input('MyMRU username: ')
        parsed_config['password'] = getpass('MyMRU password: ')

    # Logins and such for sending emails
    email_info = dict(config['Notification'].items())
    if 'password' not in email_info:
        email_info['password'] = getpass('Email Password: ')
    parsed_config['email_info'] = email_info
    parsed_config['admin_email'] = email_info['admin_email']
    del email_info['admin_email']

    # Retrieve raw course configs for all sections that start with 'Class'
    course_sections = [s for s in config.sections() if s.startswith('Class')]
    raw_courses = [config[s] for s in course_sections]

    # Sort all the raw course configs by the course number. Making a list of sections to monitor.
    merged_courses = {}
    for raw_course in raw_courses:
        n = raw_course['number']
        if n not in merged_courses:
            merged_courses[n] = dict(raw_course.items())
            merged_courses[n]['sections'] = [merged_courses[n]['section'], ]
            del merged_courses[n]['section']
        else:
            merged_courses[n]['sections'].append(raw_course['section'])

    courses = []
    for course in merged_courses.values():
        course_info = {
            'client_email'     : course['client_email'],
            'name'             : course['name'],
            'number'           : course['number'],
            'term'             : course['term'],
            'subject'          : course['subject'],
            'desired_sections' : course['sections'],
        }

        c = Course(**course_info)
        courses.append(c)
    parsed_config['courses'] = courses

    return parsed_config


def main():
    CONFIG_FILE = 'class_monitor.conf'

    config         = read_config(CONFIG_FILE)
    username       = config['username']
    password       = config['password']
    email_info     = config['email_info']
    check_interval = int(config['check_interval'])
    courses        = config['courses']
    admin_email    = config['admin_email']
    print(admin_email)

    print("Courses:")
    for course in courses:
        c = course.__str__()
        c = c.split('\n')
        c = ['  '+i for i in c]
        c = '\n'.join(c)
        print(c)

    while True:
        try:
            check_courses(username, password, email_info, courses)
            print("Checked courses. Waiting for {} minutes before checking again.".format(check_interval))
        except Exception as e:
            print("Failed to check courses: {}".format(e))
            notify_email("Failed to check courses: {}".format(e), **email_info, client=admin_email)
        time.sleep(check_interval * 60)


if __name__ == '__main__':
		try:
				main()
		except:
				send_text("Class monitor crashed")
