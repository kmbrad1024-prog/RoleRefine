"""Sample job descriptions and a pre-written example result for demo mode.

Demo mode lets visitors see the full interface without an API key.
The example result is clearly labeled in the UI as pre-written.
"""

SAMPLE_JDS = {
    "Software Engineer (biased example)": """# Senior Software Engineer

We're a young, fast-growing startup looking for a rockstar engineer who can hit the ground running. You're a competitive, aggressive problem-solver who thrives in a work hard, play hard culture and wants to dominate the market with us.

## Requirements
- Bachelor's degree in Computer Science
- 10+ years of experience with Python
- 8+ years of experience with AWS
- Expert in React, Go, Rust, and Kubernetes
- Digital native who lives and breathes tech
- Must be a strong culture fit
- Able to lift 30 lbs

## About you
You're a fearless, self-reliant ninja who takes charge and doesn't need hand-holding. He/she will lead code reviews and crush deadlines.""",

    "Sales Representative (biased example)": """Sales Ninja Wanted!

Join our young and energetic team of guys who love to win. We need an aggressive closer who can crush quotas in a competitive environment.

Requirements:
- Bachelor's degree required
- 5+ years of B2B sales
- Recent graduate energy
- Must be able to drive and stand for long periods
- Dominant personality""",

    "Customer Success Manager (fairly inclusive)": """## Customer Success Manager

You'll help our customers get the most out of our platform, working closely with product and support teams to understand their goals and solve problems together.

## What you'll need
- 2+ years in customer success, account management, or a similar role
- Clear written and verbal communication
- Comfort with CRM tools such as Salesforce or HubSpot

## Nice to have
- Experience with B2B software

Salary range: $70,000–$85,000. We offer flexible hours and remote work. We are an equal-opportunity employer.""",
}

DEMO_SAMPLE = "Software Engineer (biased example)"

DEMO_RESULT = {
    "rewritten_jd": """# Senior Software Engineer

We're a growing startup looking for an experienced engineer to help us build and scale our platform. You enjoy solving hard problems, you care about quality, and you like working with a team that ships often and learns together.

## What you'll need
- 10+ years of experience with Python
- 8+ years of experience with AWS
- Familiarity with modern web frameworks such as React

## Nice to have
- Experience with Go, Rust, or Kubernetes
- A degree in Computer Science or equivalent experience

## About you
You take ownership of your work, communicate clearly, and are comfortable making decisions with incomplete information. You'll lead code reviews and help the team deliver on time.""",
    "changes": [
        {"original": "young, fast-growing startup", "replacement": "growing startup", "category": "age",
         "reason": "'Young' can signal a preference for younger employees."},
        {"original": "rockstar engineer", "replacement": "experienced engineer", "category": "masculine_coded",
         "reason": "'Rockstar' is vague and masculine-coded; a plain description is clearer."},
        {"original": "hit the ground running", "replacement": "", "category": "exclusionary_language",
         "reason": "This idiom suggests there will be no onboarding, which discourages career changers and returners."},
        {"original": "competitive, aggressive problem-solver", "replacement": "enjoy solving hard problems", "category": "masculine_coded",
         "reason": "'Competitive' and 'aggressive' are masculine-coded and describe temperament rather than skill."},
        {"original": "work hard, play hard culture", "replacement": "a team that ships often and learns together", "category": "exclusionary_language",
         "reason": "'Work hard, play hard' can signal long hours and after-work socializing, which deters caregivers and others."},
        {"original": "dominate the market", "replacement": "build and scale our platform", "category": "masculine_coded",
         "reason": "'Dominate' is strongly masculine-coded."},
        {"original": "Expert in React, Go, Rust, and Kubernetes", "replacement": "Familiarity with React; Go, Rust, or Kubernetes as nice-to-haves", "category": "inflated_requirements",
         "reason": "Requiring expertise in four technologies is unrealistic; split into essentials and nice-to-haves."},
        {"original": "Bachelor's degree in Computer Science", "replacement": "A degree in Computer Science or equivalent experience (nice to have)", "category": "inflated_requirements",
         "reason": "Many strong engineers are self-taught or bootcamp-trained."},
        {"original": "Digital native who lives and breathes tech", "replacement": "", "category": "age",
         "reason": "'Digital native' implies a younger candidate; the technical skills are already listed."},
        {"original": "Must be a strong culture fit", "replacement": "", "category": "exclusionary_language",
         "reason": "'Culture fit' often rewards sameness; the values are better described directly."},
        {"original": "Able to lift 30 lbs", "replacement": "", "category": "ability",
         "reason": "Lifting isn't an essential duty of a software engineering role."},
        {"original": "fearless, self-reliant ninja who takes charge and doesn't need hand-holding", "replacement": "take ownership of your work, communicate clearly, and are comfortable making decisions", "category": "masculine_coded",
         "reason": "'Fearless', 'self-reliant', and 'ninja' are masculine-coded; describing behaviors is clearer."},
        {"original": "He/she", "replacement": "You", "category": "exclusionary_language",
         "reason": "'He/she' excludes nonbinary candidates; addressing the reader as 'you' is more direct."},
        {"original": "crush deadlines", "replacement": "help the team deliver on time", "category": "masculine_coded",
         "reason": "'Crush' is aggressive jargon."},
    ],
    "suggestions": [
        "Add a salary range; many candidates skip postings without one, and several US states require it.",
        "Add benefits, flexibility, and remote-work details.",
        "Add an equal-opportunity statement.",
        "10+ years of Python plus 8+ years of AWS is a very high bar that shrinks the pool; consider whether a lower minimum would still meet your needs.",
    ],
    "summary": "Removed masculine-coded and age-signaling language, a non-essential physical requirement, and exclusionary idioms. Cut the must-have list from 7 items to 3 by moving optional skills to nice-to-haves; the stated years of experience are kept, with a suggestion to review them. The tone stays energetic and startup-casual.",
}
