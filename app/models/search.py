from app import db
from datetime import datetime

class Search(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    results_count = db.Column(db.Integer)

    def to_dict(self):
        return {
            'id': self.id,
            'query': self.query,
            'timestamp': self.timestamp.isoformat(),
            'results_count': self.results_count
        }