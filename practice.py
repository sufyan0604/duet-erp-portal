import json
import os

# File to store student records
DATA_FILE = "students_data.json"


def load_data():
    """File se data load karta hai agar file exist karti ho."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                return {}
    return {}


def save_data(students):
    """Data ko JSON file mein save karta hai."""
    with open(DATA_FILE, "w") as file:
        json.dump(students, file, indent=4)


def add_student(students):
    """Naya student add karta hai."""
    print("\n--- Add New Student ---")
    roll_no = input("Enter Roll Number: ").strip()

    if roll_no in students:
        print("❌ Error: Is Roll Number ka student pehle se majood hai!")
        return

    name = input("Enter Student Name: ").strip()
    age = input("Enter Age: ").strip()
    course = input("Enter Course (e.g., Python, Web Dev): ").strip()

    students[roll_no] = {"name": name, "age": age, "course": course}

    save_data(students)
    print(f"✅ Student '{name}' successfully add ho gaya hai!")


def view_students(students):
    """Tamam students ki list dikhata hai."""
    print("\n--- All Student Records ---")
    if not students:
        print("ℹ️ Koi records nahi mile.")
        return

    print(f"{'Roll No':<10} | {'Name':<20} | {'Age':<5} | {'Course':<15}")
    print("-" * 60)
    for roll_no, info in students.items():
        print(
            f"{roll_no:<10} | {info['name']:<20} | {info['age']:<5} | {info['course']:<15}"
        )


def search_student(students):
    """Roll number se student search karta hai."""
    print("\n--- Search Student ---")
    roll_no = input("Enter Roll Number to search: ").strip()

    if roll_no in students:
        info = students[roll_no]
        print(f"\n✅ Record Found:")
        print(f"   Name   : {info['name']}")
        print(f"   Age    : {info['age']}")
        print(f"   Course : {info['course']}")
    else:
        print("❌ Is Roll Number ka koi student nahi mila.")


def delete_student(students):
    """Student record delete karta hai."""
    print("\n--- Delete Student ---")
    roll_no = input("Enter Roll Number to delete: ").strip()

    if roll_no in students:
        removed_student = students.pop(roll_no)
        save_data(students)
        print(f"🗑️ Student '{removed_student['name']}' ka record delete ho gaya.")
    else:
        print("❌ Record nahi mila.")


def main():
    """Main Menu loop."""
    students = load_data()

    while True:
        print("\n======================================")
        print("    STUDENT MANAGEMENT SYSTEM         ")
        print("======================================")
        print("1. Add Student")
        print("2. View All Students")
        print("3. Search Student")
        print("4. Delete Student")
        print("5. Exit")

        choice = input("\nSelect an option (1-5): ").strip()

        if choice == "1":
            add_student(students)
        elif choice == "2":
            view_students(students)
        elif choice == "3":
            search_student(students)
        elif choice == "4":
            delete_student(students)
        elif choice == "5":
            print("\nProgram band ho raha hai. Goodbye! 👋")
            break
        else:
            print("❌ Invalid option! 1 se 5 ke darmiyan select karein.")


# Program yahan se start hota hai
if __name__ == "__main__":
    main()