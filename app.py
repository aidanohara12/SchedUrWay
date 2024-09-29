from flask import Flask, render_template, request, redirect, url_for
from pittapi import course as pitt
from flask_sqlalchemy import SQLAlchemy
import datetime

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()


app = Flask(__name__)
db = SQLAlchemy()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
db.init_app(app)

class course_grouping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(10), nullable=False)
    course_code = db.Column(db.String(10), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    days = db.Column(db.String(10), nullable=False)
    recitation_start_time = db.Column(db.Time, nullable=True)
    recitation_end_time = db.Column(db.Time, nullable=True)
    recitation_day = db.Column(db.String(10), nullable=True)
    index = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return '%r' % self.course_code

with app.app_context():
    db.create_all()

search_results = []

@app.route('/', methods=['POST', 'GET'])
def index():
    if request.method == 'POST':
        #try:
        search_results.clear()
        cur_course_details = pitt.get_course_details(term='2251', subject=request.form['sub'], course=request.form['code'])
        lecture = None;
        num_recitations = -1
        i = 0

        for section in cur_course_details.sections:
            if(section.section_type == "Lecture"):
                if(num_recitations == 0):
                    hour_mins = lecture.start_time.split('.')
                    start_time = datetime.time(hour=int(hour_mins[0]), minute=int(hour_mins[1]))
                    hour_mins = lecture.end_time.split('.')
                    end_time = datetime.time(hour=int(hour_mins[0]), minute=int(hour_mins[1]))
                    new_course = course_grouping(subject=cur_course_details.course.subject_code, 
                                                    course_code=cur_course_details.course.course_number,
                                                    start_time=start_time, end_time=end_time,
                                                    days=lecture.days, index=i)
                    search_results.append(new_course)
                    i += 1

                lecture = section.meetings[0]
                num_recitations = 0
            else:
                for meeting in section.meetings:
                    hour_mins = lecture.start_time.split('.')
                    start_time = datetime.time(hour=int(hour_mins[0]), minute=int(hour_mins[1]))
                    hour_mins = lecture.end_time.split('.')
                    end_time = datetime.time(hour=int(hour_mins[0]), minute=int(hour_mins[1]))
                    hour_mins = meeting.start_time.split('.')
                    recitation_start_time = datetime.time(hour=int(hour_mins[0]), minute=int(hour_mins[1]))
                    hour_mins = meeting.end_time.split('.')
                    recitation_end_time = datetime.time(hour=int(hour_mins[0]), minute=int(hour_mins[1]))

                    new_course = course_grouping(subject=cur_course_details.course.subject_code, 
                                                course_code=cur_course_details.course.course_number,
                                                start_time=start_time, end_time=end_time,
                                                days=lecture.days, recitation_start_time=recitation_start_time,
                                                recitation_end_time=recitation_end_time, recitation_day=meeting.days,
                                                index=i)
                    search_results.append(new_course)
                    i += 1
                    num_recitations += 1

        return render_template('class_search.html', print = search_results)
       # except:
            #return "There was an issue"

    else:
        return render_template('class_search.html')

@app.route('/add/<int:index>')
def add(index):
    class_to_add = search_results[index]

    db.session.add(class_to_add)
    db.session.commit()
    
    added_class = course_grouping.query.all()

    class_to_be_scheduled = []
    
    for added in added_class :
        class_name = f"{added.subject} {added.course_code}, Days: {added.days}, Start time {added.start_time}, End Time {added.end_time}, Recitaion Day: {added.recitation_day}, Recitaion Start: {added.recitation_start_time}, Recitaion End: {added.recitation_end_time}"
        class_to_be_scheduled.append(class_name)

    class_gpt = ""
    for message in class_to_be_scheduled:
        class_gpt = class_gpt + " " + message

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a schedule builder"},
            {"role": "user", "content": f"Please create a comprehensive class schedule for the upcoming semester that includes the following classes and their respective times. Ensure there are no overlapping classes, and every selected class is consistent in timing throughout the semester. If there are any overlaps, please select alternative options or omit conflicting classes. Each class must only occur on the specified days. The classes are in the Format 'Class, Days(MoTuWeThFr),Startime, endtime, recitation day, recitation start time, recitation end time " + class_gpt + ". Steps to follow exactly. do not change the steps. 1. Chose class 2. See dates and times and chose a time option of times and fill out the schedule for every date assigned for that class. 3. go to next class 4. Select that classes date and time 5. if that class would overlap with a class currently on the schedule then chose another time given. If that time also overlaps, then go back to the other class and remove it from the schedule and chose another time given and fill the schedule back out for all times day days for that class. If then the chosen class has no overlaps then add it to the schedule and move to step 3. (ex a class from 10-11 overlaps with a class from 10:30-11:30) (ex a class from 10-11 also overlaps with a class from 11-12) please give me the schedule in the format 'Mon Class(Times)!Class(Times)!,Tues Class(Times)!Class(Times)!,Wed Class(Times)!Class(Times)!,Thur Class(Times)!Class(Times)!,Fri Class(Times)!Class(Times)!' This output should be one line and the only thing ever returned. if a day has no classes just say 'Mon Class(Times)!Class(Times)!,Tues,Wed Class(Times)!Class(Times)!' for every day of the week. If a class does not fit in schedule after running algorithm just leave it out."}
        ]
    )

    output = response.choices[0].message.content
    
    
    
    
    return render_template('class_search.html', print = search_results, ai_output = output)

@app.route('/myclasses')
def myclasses():
    monday_classes = course_grouping.query.filter(course_grouping.days.contains("Mo")).all()
    monday_classes.extend(course_grouping.query.filter(course_grouping.recitation_day.contains("Mo"),
                                                       course_grouping.days.not_like('%Mo%')).all())

    tuesday_classes = course_grouping.query.filter(course_grouping.days.contains("Tu")).all()
    tuesday_classes.extend(course_grouping.query.filter(course_grouping.recitation_day.contains("Tu"),
                                                        course_grouping.days.not_like('%Tu%')).all())

    wednesday_classes = course_grouping.query.filter(course_grouping.days.contains("We")).all()
    wednesday_classes.extend(course_grouping.query.filter(course_grouping.recitation_day.contains("We"),
                                                          course_grouping.days.not_like('%We%')).all())

    thursday_classes = course_grouping.query.filter(course_grouping.days.contains("Th")).all()
    thursday_classes.extend(course_grouping.query.filter(course_grouping.recitation_day.contains("Th"),
                                                         course_grouping.days.not_like('%Th%')).all())

    friday_classes = course_grouping.query.filter(course_grouping.days.contains("Fr")).all()
    friday_classes.extend(course_grouping.query.filter(course_grouping.recitation_day.contains("Fr"),
                                                       course_grouping.days.not_like('%Fr%')).all())

    return render_template('myclasses.html', mo=monday_classes, tu=tuesday_classes, we=wednesday_classes,
                            th=thursday_classes, fr=friday_classes)

if __name__ == "__main__":
    app.run(debug=True)