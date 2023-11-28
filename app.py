# Import necessary modules
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, IntegerField, SubmitField
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from sqlalchemy import text
import os
import pandas as pd
import plotly.express as px
import requests

# Create the Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 'default_value')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['API_KEY'] = os.getenv('API_KEY', 'your_api_key')  # Set your API key in env var


db = SQLAlchemy(app)

# Define the ASINData model
class ASINData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asin = db.Column(db.String(10), nullable=False)
    category1_name = db.Column(db.String(50), nullable=False)
    category1_rank = db.Column(db.Integer, nullable=False)
    category2_name = db.Column(db.String(50), nullable=False)
    category2_rank = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# Testing the database connection
try:
    with app.app_context():
        db.session.execute(text('SELECT 1')).fetchall()
        print("Database connection established successfully.")
except Exception as e:
    print(f"Failed to connect to the database. Error: {str(e)}")

# Creating the tables within the application context
with app.app_context():
    db.create_all()

# Function to validate API key
def validate_api_key():
    api_key = request.headers.get('Api-Key')
    if api_key != app.config['API_KEY']:
        return jsonify({"error": "Invalid API key"}), 401
    return None  # Proceed with the request

# Add before_request decorator to validate API key before each request
@app.before_request
def before_request():
    return validate_api_key()

# Route to input ASIN and category data to the API
@app.route('/', methods=['GET'])
def input_data():
    asin = request.args.get('asin', '')
    category1_name = request.args.get('category1_name', '')
    category1_rank = int(request.args.get('category1_rank', 0) or 0)
    category2_name = request.args.get('category2_name', '')
    category2_rank = int(request.args.get('category2_rank', 0) or 0)

    if not any([asin, category1_name, category2_name]):
        return jsonify({"message": "No input data provided."})

    # Store the data in the database
    with app.app_context():
        new_entry = ASINData(asin=asin, category1_name=category1_name,
                            category1_rank=category1_rank,
                            category2_name=category2_name,
                            category2_rank=category2_rank)
        db.session.add(new_entry)
        db.session.commit()

    return jsonify({"message": "Data received and stored successfully!"})

# Function to generate a chart for a specific category
def generate_category_chart(asin, df, category, title_suffix):
    fig = px.line(df, x='date', y=f'{category}_rank', title=f'{df[category + "_name"].iloc[0]} {title_suffix} Rank over Time')
    fig.update_yaxes(title_text='')

    # Highlight the current data point for each day
    custom_data = df[f'{category}_rank']
    hover_data = {
        'date': df['date'],
        'rank': custom_data,
    }
    scatter_trace = px.scatter(df, x='date', y=fig.data[0].y)
    scatter_trace.update_traces(hovertemplate='%{customdata[0]} - Rank: %{customdata[1]}',
                                customdata=list(zip(df['date'], custom_data)))
    fig.add_trace(scatter_trace.data[0])

    # Add ASIN at the top
    fig.update_layout(title_text=f'{asin} - {df[category + "_name"].iloc[0]} ', title_x=0.5)

    # Set the maximum length for category name in the chart title
    max_category_name_length = 75
    fig.layout.title.text = fig.layout.title.text[:max_category_name_length]

    return fig.to_html(full_html=False)

# Route to generate charts for a specific ASIN
@app.route('/api/charts/<asin>', methods=['GET'])
def generate_charts(asin):
    try:
        # Query data from the database for the specified ASIN
        with app.app_context():
            data = ASINData.query.filter_by(asin=asin).all()

        # Convert the data to a DataFrame
        df = pd.DataFrame([(entry.timestamp, entry.category1_name, entry.category1_rank,
                            entry.category2_name, entry.category2_rank) for entry in data],
                          columns=['timestamp', 'category1_name', 'category1_rank', 'category2_name', 'category2_rank'])

        # Add 'date' column to the DataFrame
        df['date'] = pd.to_datetime(df['timestamp']).dt.floor('D').dt.strftime('%B %d, %Y')

        # Check the number of unique categories with data
        unique_categories = df[['category1_name', 'category2_name']].nunique().gt(0)
        num_categories_with_data = unique_categories.sum()

        if num_categories_with_data == 1:
            # Generate chart for the available category
            available_category = unique_categories[unique_categories].index[0]
            chart = generate_category_chart(asin, df, available_category, 'Rank over Time')
            return jsonify({"chart1": chart})

        elif num_categories_with_data == 2:
            # Generate charts for both categories
            chart1 = generate_category_chart(asin, df, 'category1', 'Rank over Time')
            chart2 = generate_category_chart(asin, df, 'category2', 'Rank over Time')
            return jsonify({"chart1": chart1, "chart2": chart2})

        else:
            # No category data available
            return jsonify({"message": "No category data available for the specified ASIN."})

    except Exception as e:
        return jsonify({"error": str(e)})

# Entry point for Gunicorn
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)