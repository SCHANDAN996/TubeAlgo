# run.py
# No async monkey patching for now - using sync workers

from tubealgo import create_app

app = create_app()
# Make celery instance available for worker/beat commands
celery = app.celery

if __name__ == '__main__':
    # Set debug=False for production or Render deployment
    # Port is usually handled by Gunicorn or Render's environment
    app.run(debug=False)
