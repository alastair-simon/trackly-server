from flask import Blueprint, request, jsonify
from app import db
from app.models.search import Search
from app.utils.search_util import perform_search

search_bp = Blueprint('search', __name__)

@search_bp.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    query = data.get('query')

    if not query:
        return jsonify({'error': 'Query parameter required'}), 400

    # Perform search using your util
    results = perform_search(query)

    # Save search to database
    search_record = Search(
        query=query,
        results_count=len(results) if isinstance(results, list) else 0
    )
    db.session.add(search_record)
    db.session.commit()

    return jsonify({
        'query': query,
        'results': results,
        'search_id': search_record.id
    })

@search_bp.route('/search/history', methods=['GET'])
def search_history():
    searches = Search.query.order_by(Search.timestamp.desc()).all()
    return jsonify([search.to_dict() for search in searches])