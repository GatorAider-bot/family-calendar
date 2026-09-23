import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, request, session, url_for
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Google Calendar API setup
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CLIENT_SECRETS_FILE = 'credentials.json'

def get_calendar_service():
    """Get authenticated Google Calendar service"""
    if 'credentials' not in session:
        return None

    creds = Credentials(**session['credentials'])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        session['credentials'] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }

    return build('calendar', 'v3', credentials=creds)

def get_events():
    """Get events for today and next 6 days"""
    service = get_calendar_service()
    if not service:
        return None

    now = datetime.utcnow().isoformat() + 'Z'
    end = (datetime.utcnow() + timedelta(days=6)).isoformat() + 'Z'

    try:
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=end,
            singleEvents=True,
            orderBy='startTime',
            maxResults=50
        ).execute()

        return events_result.get('items', [])
    except Exception as e:
        print(f"Error fetching events: {e}")
        return None

def format_events_by_day(events):
    """Group events by day"""
    if not events:
        return {}

    days = {}
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        try:
            event_date = datetime.fromisoformat(start.replace('Z', '+00:00')).date()
        except:
            event_date = datetime.fromisoformat(start).date()

        day_key = event_date.isoformat()

        if day_key not in days:
            days[day_key] = []

        days[day_key].append(event)

    return days

def format_event_time(event):
    """Format event time for display"""
    start = event['start'].get('dateTime', event['start'].get('date'))

    if 'T' not in start:
        return "All day"

    try:
        dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        return dt.strftime('%I:%M %p')
    except:
        return start

@app.route('/')
def index():
    """Main calendar view"""
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

    events = get_events()
    if events is None:
        return redirect(url_for('authorize'))

    events_by_day = format_events_by_day(events)

    # Format for display
    display_days = []
    for i in range(7):
        date = datetime.utcnow().date() + timedelta(days=i)
        day_key = date.isoformat()
        day_events = events_by_day.get(day_key, [])

        # Sort events by time
        day_events.sort(key=lambda e: e['start'].get('dateTime', e['start'].get('date')))

        display_days.append({
            'date': date,
            'day_name': date.strftime('%A'),
            'date_str': date.strftime('%b %d'),
            'is_today': date == datetime.utcnow().date(),
            'events': [
                {
                    'title': event.get('summary', 'No title'),
                    'time': format_event_time(event),
                    'location': event.get('location', ''),
                    'description': event.get('description', '')
                }
                for event in day_events
            ]
        })

    return render_template('index.html', days=display_days)

@app.route('/authorize')
def authorize():
    """Start OAuth flow"""
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=os.environ.get('REDIRECT_URI', 'http://localhost:5000/callback')
        )

        auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
        session['state'] = state

        return redirect(auth_url)
    except FileNotFoundError:
        return "Error: credentials.json not found. Please set up Google API credentials.", 500

@app.route('/callback')
def callback():
    """OAuth callback"""
    state = session.get('state')
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=os.environ.get('REDIRECT_URI', 'http://localhost:5000/callback')
    )

    try:
        flow.fetch_token(authorization_response=request.url)

        credentials = flow.credentials
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }

        return redirect(url_for('index'))
    except Exception as e:
        print(f"Auth error: {e}")
        return "Authentication failed", 500

@app.route('/logout')
def logout():
    """Clear session"""
    session.clear()
    return redirect(url_for('authorize'))

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
