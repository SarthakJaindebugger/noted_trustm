# -*- coding: utf-8 -*-
"""
common/questions.py
=====================
The structured questionnaire (question groups) used by stage 4, moved out
of privacy_rag_2_outputs.py so it is data, not code buried in the middle
of the pipeline logic.
"""

QUESTION_GROUPS = [
    {"id": "GROUP 1", "questions": [
        {"id": "Ques.5", "text": "What is the contact method used by Advisee(s)?", "options": [
            "a) Visit for guidance/advice in-person",
            "b) Telephone (eg. call, WhatsApp etc)",
            "c) Written Contact (eg. email, WhatsApp, social media etc)",
            "d) Remote Connection",
            "e) Electronic service (eg. forms)",
            "f) Field Work (if yes then where)"]},
        {"id": "Ques.6", "text": "Heard from the guidance/advice position (if other where?)", "options": [
            "a) Digital and population data services agency",
            "b) Organisation/association",
            "c) Reel",
            "d) Municipal integration/immigrant services",
            "e) Multicultural Centre",
            "f) Marketing communications of the control point",
            "g) Educational institution",
            "h) Participatory Center",
            "i) Congregation/religious community",
            "j) Social services",
            "k) Relatives/acquaintances",
            "l) TE Services",
            "m) Employer",
            "n) Shared service point",
            "o) Visited in the past",
            "p) Other",
            "r) No information"]},
    ]},
    {"id": "GROUP 2", "questions": [
        {"id": "Ques.10", "text": "Reason for Immigration", "options": None},
    ]},
    {"id": "GROUP 3", "questions": [
        {"id": "Ques.11", "text": "Additional Information about the customers", "options": [
            "a) Illiterate", "b) Paperless", "c) Tourist", "d) Ukraine Crisis", "e) If something else type"],
         "allow_other": True},
        {"id": "Ques.14", "text": "Education Level", "options": None},
    ]},
    {"id": "GROUP 4", "questions": [
        {"id": "Ques.12", "text": "Customer birth country", "options": None},
        {"id": "Ques.13", "text": "Mother Tongue/Language", "options": None},
        {"id": "Ques.16", "text": "Customer Domicile", "options": None},
    ]},
    {"id": "GROUP 5", "questions": [
        {"id": "Ques.15", "text": "Position in labour market", "options": [
            "a) No Information", "b) Working in the open market",
            "c) Working outside the open market (eg.: wage subsidy, work trail)",
            "d) Entrepreneur", "e) Unemployed",
            "f) In labour policy training (including integration training)",
            "g) Student", "h) Outside the labour market (eg.: stay-home-parent, retiree)",
            "i) Planning to move to Finland"]},
    ]},
    {"id": "GROUP 6", "questions": [
        {"id": "Ques.17", "text": "Duration of residence in Finland", "options": [
            "a) No information", "b) Does not live in Finland", "c) Less than 3 years",
            "d) 3-5 years", "e) More than 5 years"]},
    ]},
    {"id": "GROUP 7", "questions": [
        {"id": "Ques.18", "text": "Contents of the customer visit:", "options": [
            "a) Residence", "b) Benefits (eg.: Kela)", "c) Hobbies & Leisures",
            "d) Matters related to education", "e) Crisis situations (family crisis, violent situations)",
            "f) Matters related to immigration process (eg.: residence permit)", "g) Legal Matters",
            "h) Family life (eg.: children's school, early childhood education, relationships)",
            "i) Police matters", "j) Social Affairs (eg.: social work, guidance)",
            "k) Studying Finnish/Swedish",
            "l) Finance (eg.: taxation, debt, bills, banking, and customer affairs)",
            "m) Health care", "n) Working conditions (eg.: occupational health safety)",
            "o) Work (eg.: TE, Job search, etc)", "p) Career Guidance", "q) If other, then type"],
         "allow_other": True},
        {"id": "Ques.19", "text": "Purpose of visit", "options": [
            "a) Initial Interview", "b) Digital Help", "c) Language Support", "d) Filling out the forms",
            "e) Clarification of decisions and process", "f) Group info",
            "g) Contacting the authority of another country", "h) Others"],
         "allow_other": True},
    ]},
    {"id": "GROUP 8", "questions": [
        {"id": "Ques.21", "text": "Where the customer is directed", "options": [
            "a) Trade-unions, occupational safety and health", "b) Lawyer and legal aid services",
            "c) Real estate agency/real estate, housing agency", "d) Digital and Population Information Agency",
            "e) Victims of human trafficking", "f) help system", "g) Organizations and associations",
            "h) School activity (basic education)", "i) Crisis services",
            "j) Municipal immigrant and integration services", "k) Finnish Immigration Service (Migri)",
            "l) Youth services (e.g., Ohjaamo)", "m) Educational institution (secondary school, higher education or other)",
            "n) Police", "o) Congregations and other religious communities", "p) Social and family services",
            "q) Embassy", "r) TE services", "s) Health services", "t) Customs", "u) Early childhood education",
            "v) Tax office", "w) Shared service point", "x) Support services for entrepreneurs",
            "y) Companies/employers", "z) Other entities", "aa) Case closed",
            "ab) Customer service continues/Make a new appointment",
            "ac) Guidance and counseling service in another location"],
         "allow_other": False},
    ]},
]
