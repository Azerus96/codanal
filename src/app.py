from flask import Flask, render_template, request, jsonify
from analyzer import CodeAnalyzer
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    repo_url = request.form.get('repo_url')
    if not repo_url:
        return jsonify({"error": "Repository URL is required"})
    
    try:
        analyzer = CodeAnalyzer()
        analyzer.start()
        try:
            results = analyzer.analyze_repository(repo_url)
            return jsonify(results)
        finally:
            analyzer.close()
            
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
