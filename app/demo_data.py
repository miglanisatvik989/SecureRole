"""Reproducible fictional rosters for the expanded classroom demonstration."""

from dataclasses import dataclass
from itertools import product
from random import Random

from app.seed import DEMO_ACCOUNTS

SUBJECTS = (
    "Cryptography and Network Security",
    "Data Structures and Algorithms",
    "Database Management Systems",
    "Operating Systems",
    "Computer Networks",
    "Artificial Intelligence",
)
EMAIL_DOMAIN = "securerole.example"
RECORD_TOTAL = 110

FIRST_NAMES = (
    "Aarav", "Aditi", "Aditya", "Akanksha", "Ananya", "Aniket", "Anjali", "Arjun",
    "Avani", "Bhavya", "Charu", "Deepak", "Devika", "Diksha", "Diya", "Farah",
    "Gaurav", "Ishaan", "Jaya", "Kabir", "Kavya", "Kiran", "Lakshmi", "Manav",
    "Meera", "Mihir", "Naina", "Neha", "Nikhil", "Pallavi", "Parth", "Pranav",
    "Priya", "Radhika", "Rahul", "Rekha", "Riya", "Rohan", "Rudra", "Saanvi",
    "Sahil", "Sana", "Shreya", "Soham", "Tanvi", "Tarun", "Varun", "Veena",
    "Vihaan", "Zoya",
)
LAST_NAMES = (
    "Agarwal", "Bhat", "Bose", "Chandra", "Das", "Desai", "Dutta", "Ghosh",
    "Gowda", "Iyer", "Jain", "Joshi", "Kapoor", "Kulkarni", "Menon", "Mishra",
    "Mukherjee", "Nair", "Patel", "Patil", "Pillai", "Rao", "Reddy", "Roy",
    "Saha", "Saxena", "Sen", "Shah", "Sharma", "Shetty", "Singh", "Verma",
)


@dataclass(frozen=True)
class DemoAccount:
    username: str
    name: str
    role: str
    teacher: str | None = None
    subject: str | None = None
    marks: float | None = None
    prefers_waiting: bool = False

    @property
    def email(self):
        return f"{self.username}@{EMAIL_DOMAIN}"


def academic_mark(rng):
    """Most marks are mid-range, with a smaller spread at both ends."""
    band = rng.choices(((35, 49), (50, 64), (65, 79), (80, 89), (90, 98)),
                       weights=(5, 16, 39, 30, 10))[0]
    return rng.randint(*band) + rng.choice((0, 0, 0.5))


def plan_demo():
    rng = Random(7241)
    originals = {name: (display, role, teacher) for name, display, role, teacher in DEMO_ACCOUNTS}
    reserved = {("Ananya", "Rao"), ("Devika", "Nair"), ("Rohan", "Sen")}
    pool = [name for name in product(FIRST_NAMES, LAST_NAMES) if name not in reserved]
    generated = iter(rng.sample(pool, 127))

    def named(parts, role, **academic):
        username = ".".join(parts).lower()
        return DemoAccount(username, " ".join(parts), role, **academic)

    def original(username, **academic):
        name, role, teacher = originals[username]
        return DemoAccount(username, name, role, teacher, **academic)

    administrators = [original("admin"), named(("Ananya", "Rao"), "Admin")]
    teachers = [original("teacher1", subject=SUBJECTS[0]), original("teacher2", subject=SUBJECTS[0])]
    teachers.extend(named(name, "Teacher", subject=SUBJECTS[1])
                    for name in (("Devika", "Nair"), ("Rohan", "Sen")))
    for subject in SUBJECTS[2:]:
        teachers.extend(named(next(generated), "Teacher", subject=subject) for _ in range(2))

    students = []
    for index, teacher in enumerate(teachers):
        cohort = []
        if index == 0:
            cohort.extend((
                original("student1", subject=teacher.subject, marks=85),
                original("student2", subject=teacher.subject, marks=academic_mark(rng), prefers_waiting=True),
            ))
        elif index == 1:
            cohort.append(original("student3", subject=teacher.subject, marks=78))
        while len(cohort) < 10:
            cohort.append(named(next(generated), "Student", teacher=teacher.username, subject=teacher.subject,
                                marks=academic_mark(rng), prefers_waiting=0 < index < 10 and len(cohort) == 9))
        students.extend(cohort)

    return tuple(administrators + teachers + students)
