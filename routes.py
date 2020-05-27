import os
import secrets
from PIL import Image
from flask import render_template, url_for, flash, redirect, request, abort
from flaskblog import app, db, bcrypt, mail
from flaskblog.forms import (RegistrationForm, LoginForm, UpdateAccountForm,
                             RequestResetForm, ResetPasswordForm)
from flaskblog.models import User, Post
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message
from neo4j import GraphDatabase



@app.route("/home")
def home():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('home.html', posts=posts)


@app.route("/about")
def about():
    return render_template('about.html', title='About')


@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)


@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/profile_pics', picture_fn)

    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn


@app.route("/account", methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Your account has been updated!', 'success')
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', title='Account',
                           image_file=image_file, form=form)


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request',
                  sender='noreply@demo.com',
                  recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made.
'''
    mail.send(msg)


@app.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_request.html', title='Reset Password', form=form)


@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html', title='Reset Password', form=form)





#after login starts here




# returns a list satisfying given parameters
def get_optimal_crop(soiltype, temperature, water, rainfall):
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"), encrypted=False)
    with driver.session() as session:
        query1 = "MATCH (c:Crop)-[]->(s:Soiltype) WHERE s.name=$soiltype RETURN c.name as value1"
        query2 = "MATCH (c:Crop)-[r]->(t:Temperature) WHERE r.min<=$temperature AND r.max>=$temperature RETURN c.name as value2"
        query3 = "MATCH (c:Crop)-[r]->(t:Water) WHERE r.min<=$water AND r.max>=$water RETURN c.name as value3"
        query4 = "MATCH (c:Crop)-[r]->(t:Rainfall) WHERE r.min<=$rainfall AND r.max>=$rainfall RETURN c.name as value4"
        tx = session.begin_transaction()
        result1 = tx.run(query1, soiltype=soiltype)
        result2 = tx.run(query2, temperature=temperature)
        result3 = tx.run(query3, water=water)
        result4 = tx.run(query4, rainfall=rainfall)
        tx.commit()
        list1 = []
        list2 = []
        list3 = []
        list4 = []
        result = []
        for record in result1:
            list1.append(record["value1"])
        for record in result2:
            list2.append(record["value2"])
        for record in result3:
            list3.append(record["value3"])
        for record in result4:
            list4.append(record["value4"])
        result = list(set(list1) & set(list2) & set(list3) & set(list4))
        driver.close()
        return result


# print(get_optimal_crop("black soil", 20, 1000, 120))
#create_database()

# returns details of about a specific crop
def get_details_of_crop(crop_name):
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"), encrypted=False)
    with driver.session() as session:
        query1 = "MATCH (c:Crop)-[r]->(s:Soiltype) WHERE c.name=$crop_name RETURN s.name as value1"
        query2 = "MATCH (c:Crop)-[r]->(t:Temperature) WHERE c.name=$crop_name RETURN r.min as min2,r.max as max2"
        query3 = "MATCH (c:Crop)-[r]->(t:Water) WHERE c.name=$crop_name RETURN r.min as min3,r.max as max3"
        query4 = "MATCH (c:Crop)-[r]->(:Rainfall) WHERE c.name=$crop_name RETURN r.min as min4,r.max as max4"
        query5 = "MATCH (c:Crop)-[r]->(h:HighestProducer) WHERE c.name=$crop_name RETURN h.name as value5"
        tx = session.begin_transaction()
        result1 = tx.run(query1, crop_name=crop_name)
        result2 = tx.run(query2, crop_name=crop_name)
        result3 = tx.run(query3, crop_name=crop_name)
        result4 = tx.run(query4, crop_name=crop_name)
        result5 = tx.run(query5, crop_name=crop_name)
        tx.commit()
        list1 = []
        list2 = []
        list3 = []
        list4 = []
        list5 = []
        for record in result1:
            list1.append(record["value1"])
        for record in result2:
            list2.append(record["min2"])
            list2.append(record["max2"])
        for record in result3:
            list3.append(record["min3"])
            list3.append(record["max3"])
        for record in result4:
            list4.append(record["min4"])
            list4.append(record["max4"])
        for record in result5:
            list5.append(record["value5"])

        result = [list1, list2, list3, list4, list5]
        driver.close()
        return result


@app.route('/')
@login_required
def formpage():
	return render_template('range.html')



@app.route('/exact')
@login_required
def formpage2():
	return render_template('exact.html')



@app.route('/process', methods=['GET', 'POST'] )
@login_required
def process():
    if request.method == 'POST':
        soil = request.form['soil']
        water = request.form['water']
        temperature  = request.form['temp']
        rain = request.form['rain'] 
        print(soil,water,rain,temperature)
        x = get_optimal_crop(str(soil),int(temperature), int(water), int(rain))
        print(x)
        #print(get_optimal_crop("black soil", 20, 1000, 120))
        
    if len(x) == 0: 
        return render_template('result.html',header='No Matching Crops found', sub_header='(Based on key parameters you provided)', list_header="Try Other Combinations instead",
                       crops=x, title="Result")
    else: 
        return render_template('result.html',header='Results', sub_header='(Based on key parameters you provided)', list_header="Crop Names",
                       crops=x, title="Result")
    

@app.route('/openform')
@login_required
def renders():
    return render_template('tenp.html')


@app.route('/process2',methods=['GET', 'POST'])
@login_required
def processs():
    if request.method == 'POST':
        crop = request.form['crop']
        y = get_details_of_crop(str(crop))
       # print(y)

        if len(y[0]) == 0: 
            soil = "-"
        else:
            soil = y[0]
            
        if len(y[1]) == 0: 
            temp = "-"
        else:
            temp = y[1]
        
        if len(y[2]) == 0: 
            water = "-"
        else:
            water = y[2]

        if len(y[3]) == 0: 
            rainfall = "-"
        else:
            rainfall = y[3]

        if len(y[4]) == 0: 
            producer = "-"
        else:
            producer = y[4]

        
        
    
    if (len(y[0]) == 0 & len(y[1]) == 0 & len(y[2]) == 0 & len(y[3]) == 0 & len(y[4]) == 0): 
        return render_template('result2.html', sub_header='(Based on key parameters you provided)', list_header="Details not found for this entry",
                       crop_name= str(crop), title="Result",soils=soil,temps=temp,waters=water,rainfalls=rainfall,producers=producer)
    else: 
        return render_template('result2.html', sub_header='(Based on key parameters you provided)', list_header="Details",
                       crop_name= str(crop), title="Result",soils=soil,temps=temp,waters=water,rainfalls=rainfall,producers=producer)

    




