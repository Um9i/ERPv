<span align="center">

<p align="center">
  <img width="100" height="50" src="erpv.png">
</p>

**_Open Source Enterprise Resource Planning._**

[![Code style: black](https://img.shields.io/badge/code%20style-black-black.svg)](https://github.com/ambv/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

</span>


ERPv is a business management tool which currently includes management of the following functions.

* Inventory
* Manufacturing
* Procurement
* Sales

# Development Setup

## Requirements

* [Python 3.10](https://www.python.org/)

## Process

1. Install the required dependencies with pip.

```
pip install -r requirements.txt
```

2. Run database migrations to setup the database.

```
python manage.py migrate
```

3. Create a user.

```
python manage.py createsuperuser
```

4. Run the server.

```
python manage.py runserver
```