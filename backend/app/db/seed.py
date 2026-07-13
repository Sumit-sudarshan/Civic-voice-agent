import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlmodel import Session, select
from app.db.session import engine, create_db_and_tables
from app.models.db_models import Complaint, SubmissionType, Category, UrgencyLevel, Status

def seed_db():
    create_db_and_tables()
    with Session(engine) as session:
        existing = session.exec(select(Complaint)).first()
        if existing:
            print("Database already seeded.")
            return

        print("Seeding database with 15 demo records...")
        complaints = [
            # --- COMPLAINTS ---
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="The main water pipe burst in front of the school and the road is flooded.",
                citizen_name="Rahul", citizen_last_name="Sharma",
                citizen_phone="9876543210",
                location_address="In front of the government primary school",
                location_area="Vrindavan Colony", location_pincode="400021",
                category=Category.water,
                urgency_level=UrgencyLevel.critical,
                urgency_reasoning="Flooding near a school poses immediate safety and health risks.",
                extracted_location="In front of the school, Vrindavan Colony, 400021", extracted_issue_summary="Burst water pipe flooding road",
                extracted_affected_parties="School children, commuters", extracted_ask="Fix the pipe and clear the water",
                status=Status.open, is_valid_submission=True, needs_human_review=False
            ),
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="Streetlight flickering outside my house for over a week. Very unsafe at night.",
                citizen_name="Priya", citizen_last_name="Nair",
                citizen_phone="9876543211",
                location_address="Outside her house, Shastri Nagar",
                location_area="Shastri Nagar", location_pincode="400012",
                category=Category.electricity,
                urgency_level=UrgencyLevel.medium,
                urgency_reasoning="Flickering streetlight is an inconvenience but not an immediate hazard.",
                extracted_location="Shastri Nagar", extracted_issue_summary="Flickering streetlight",
                extracted_affected_parties="Local residents", extracted_ask="Repair the streetlight",
                status=Status.in_progress, is_valid_submission=True, needs_human_review=False
            ),
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="There is a massive pothole on MG Road near the bus stop. Two bikes fell today.",
                citizen_name="Suresh", citizen_last_name="Patil",
                citizen_phone="9876543213",
                location_address="MG Road, near the bus stop",
                location_area="Koramangala", location_pincode="560034",
                category=Category.roads,
                urgency_level=UrgencyLevel.high,
                urgency_reasoning="Active accidents reported — road hazard is causing immediate injuries.",
                extracted_location="MG Road near bus stop, Koramangala", extracted_issue_summary="Large pothole causing accidents",
                extracted_affected_parties="Commuters, bike riders", extracted_ask="Fill the pothole urgently",
                status=Status.open, is_valid_submission=True, needs_human_review=False, report_count=3
            ),
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="Garbage not collected for 2 weeks. Rats and mosquitoes everywhere.",
                citizen_name="Fatima", citizen_last_name="Sheikh",
                citizen_phone="9876543214",
                location_address="Near the market entrance",
                location_area="Indiranagar", location_pincode="560038",
                category=Category.sanitation,
                urgency_level=UrgencyLevel.high,
                urgency_reasoning="Uncollected garbage for 2 weeks is a serious public health hazard.",
                extracted_location="Near the market entrance, Indiranagar", extracted_issue_summary="Garbage not collected for 2 weeks",
                extracted_affected_parties="Shopkeepers and market visitors", extracted_ask="Resume garbage collection immediately",
                status=Status.open, is_valid_submission=True, needs_human_review=False, report_count=5
            ),
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="The government primary school roof is leaking badly. Children sit in wet classrooms during rains.",
                citizen_name="Anjali", citizen_last_name="Kulkarni",
                citizen_phone="9876543215",
                location_address="Government Primary School",
                location_area="Jayanagar", location_pincode="560011",
                category=Category.education,
                urgency_level=UrgencyLevel.high,
                urgency_reasoning="Leaking roof in a school directly harms children's safety and education.",
                extracted_location="Government Primary School, Jayanagar", extracted_issue_summary="Leaking school roof",
                extracted_affected_parties="School children, teachers", extracted_ask="Repair the school roof before monsoon",
                status=Status.resolved, is_valid_submission=True, needs_human_review=False
            ),
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="Government clinic has no doctor after 2 PM. Patients are turned away daily.",
                citizen_name="Ramesh", citizen_last_name="Gupta",
                citizen_phone="9876543216",
                location_address="Government Clinic, main road",
                location_area="Whitefield", location_pincode="560066",
                category=Category.healthcare,
                urgency_level=UrgencyLevel.high,
                urgency_reasoning="Lack of medical staff at a government clinic affects the whole area's healthcare access.",
                extracted_location="Government Clinic, Whitefield", extracted_issue_summary="No doctor available after 2 PM",
                extracted_affected_parties="All patients in the area", extracted_ask="Assign a doctor for afternoon shift",
                status=Status.open, is_valid_submission=True, needs_human_review=False
            ),
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="Chain snatching near the ATM on Park Street every night. Police not responding.",
                citizen_name="Deepa", citizen_last_name="Menon",
                citizen_phone="9876543217",
                location_address="ATM on Park Street",
                location_area="Bandra East", location_pincode="400051",
                category=Category.safety,
                urgency_level=UrgencyLevel.critical,
                urgency_reasoning="Repeated chain snatching incidents with no police response is an active safety emergency.",
                extracted_location="ATM on Park Street, Bandra East", extracted_issue_summary="Repeated chain snatching near ATM",
                extracted_affected_parties="Residents near Park Street", extracted_ask="Increase police patrol at night",
                status=Status.open, is_valid_submission=True, needs_human_review=False, report_count=4
            ),
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="Live electrical wire hanging over the footpath since yesterday evening. Very dangerous.",
                citizen_name="Vikram", citizen_last_name="Joshi",
                citizen_phone="9876543218",
                location_address="Footpath near the bus depot",
                location_area="Andheri West", location_pincode="400058",
                category=Category.electricity,
                urgency_level=UrgencyLevel.critical,
                urgency_reasoning="Live wire on footpath is an immediate lethal electrocution hazard.",
                extracted_location="Footpath near the bus depot, Andheri West", extracted_issue_summary="Live wire hanging over footpath",
                extracted_affected_parties="Pedestrians, children", extracted_ask="Remove the wire immediately",
                status=Status.in_progress, is_valid_submission=True, needs_human_review=False
            ),
            # --- Flagged for review ---
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="The road is flooded because a water pipe burst.",
                citizen_name="Mohan", citizen_last_name="Das",
                citizen_phone="9876543219",
                location_address="not specified",
                location_area="Dadar", location_pincode="not specified",
                category=Category.water,
                urgency_level=UrgencyLevel.high,
                urgency_reasoning="Flooding caused by a burst pipe is a high-severity water infrastructure failure.",
                extracted_location="Dadar", extracted_issue_summary="Road flooded due to burst water pipe",
                extracted_affected_parties="Commuters, nearby residents", extracted_ask="Fix the pipe",
                status=Status.open, is_valid_submission=True, needs_human_review=True, review_reason="location_incomplete"
            ),
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="Open drain near the playground is overflowing. Kids playing nearby.",
                citizen_name="Sunita", citizen_last_name="Rao",
                citizen_phone="9876543220",
                location_address="Near the playground",
                location_area="Saket", location_pincode="110017",
                category=Category.sanitation,
                urgency_level=UrgencyLevel.critical,
                urgency_reasoning="Overflowing drain near a children's playground is an immediate health and safety hazard.",
                extracted_location="Near the playground, Saket", extracted_issue_summary="Overflowing open drain near playground",
                extracted_affected_parties="Children, families", extracted_ask="Clear the drain immediately",
                status=Status.open, is_valid_submission=True, needs_human_review=False
            ),
            Complaint(
                submission_type=SubmissionType.complaint,
                raw_text="No water supply in our building for 3 days. Please help.",
                citizen_name="Kavita", citizen_last_name="Pillai",
                citizen_phone="9876543221",
                location_address="Residential building, near Hauz Khas market",
                location_area="Hauz Khas", location_pincode="110016",
                category=Category.water,
                urgency_level=UrgencyLevel.high,
                urgency_reasoning="Three days without water supply is a severe public health issue.",
                extracted_location="Residential building near Hauz Khas market", extracted_issue_summary="No water supply for 3 days",
                extracted_affected_parties="All building residents", extracted_ask="Restore water supply",
                status=Status.resolved, is_valid_submission=True, needs_human_review=False, report_count=2
            ),
            # --- SUGGESTIONS ---
            Complaint(
                submission_type=SubmissionType.suggestion,
                raw_text="It would be great to have a new dustbin near the park entrance.",
                citizen_name="Amit", citizen_last_name="Singh",
                citizen_phone="9876543212",
                location_address="Park entrance",
                location_area="Jayanagar", location_pincode="560011",
                category=Category.sanitation,
                extracted_location="Park entrance, Jayanagar", extracted_issue_summary="Request for new dustbin",
                extracted_affected_parties="Park visitors", extracted_ask="Install a new dustbin",
                status=Status.open, is_valid_submission=True, needs_human_review=False
            ),
            Complaint(
                submission_type=SubmissionType.suggestion,
                raw_text="Please install solar-powered streetlights on the main road to reduce electricity costs.",
                citizen_name="Neha", citizen_last_name="Kapoor",
                citizen_phone="9876543222",
                location_address="Main road",
                location_area="Koramangala", location_pincode="560034",
                category=Category.electricity,
                extracted_location="Main road, Koramangala", extracted_issue_summary="Request for solar streetlights",
                extracted_affected_parties="All residents, municipality", extracted_ask="Install solar streetlights on main road",
                status=Status.open, is_valid_submission=True, needs_human_review=False
            ),
            Complaint(
                submission_type=SubmissionType.suggestion,
                raw_text="A speed bump near the school gate would prevent accidents. Vehicles go very fast.",
                citizen_name="Arun", citizen_last_name="Kumar",
                citizen_phone="9876543223",
                location_address="School gate",
                location_area="Vrindavan Colony", location_pincode="400021",
                category=Category.safety,
                extracted_location="School gate, Vrindavan Colony", extracted_issue_summary="Request for speed bump near school",
                extracted_affected_parties="School children, parents", extracted_ask="Install a speed bump at school gate",
                status=Status.open, is_valid_submission=True, needs_human_review=False
            ),
            Complaint(
                submission_type=SubmissionType.suggestion,
                raw_text="The waiting area at the government hospital has no fans. Patients suffer in summer.",
                citizen_name="Lata", citizen_last_name="Desai",
                citizen_phone="9876543224",
                location_address="Government Hospital",
                location_area="Whitefield", location_pincode="560066",
                category=Category.healthcare,
                extracted_location="Government Hospital, Whitefield", extracted_issue_summary="No fans in patient waiting area",
                extracted_affected_parties="Patients, visitors", extracted_ask="Install ceiling fans in waiting area",
                status=Status.in_progress, is_valid_submission=True, needs_human_review=False
            ),
        ]

        session.add_all(complaints)
        session.commit()
        print(f"Seeded {len(complaints)} records successfully!")

if __name__ == "__main__":
    seed_db()
