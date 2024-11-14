from flask import Flask, render_template, request, jsonify
from playwright.sync_api import sync_playwright
from github import Github
import logging
from urllib.parse import urlparse
import base64

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CodeAnalyzer:
    def __init__(self, ai_service_url="https://gpt-o-1.ru/app/chat/"):  # Замените на URL вашего AI сервиса
        self.ai_service_url = ai_service_url
        self.playwright = None
        self.browser = None
        self.page = None
        self.logger = logging.getLogger(__name__)

    def start(self):
        """Инициализация браузера"""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            self.page = self.browser.new_page()
            self._login_to_ai_service()
        except Exception as e:
            self.logger.error(f"Failed to start browser: {str(e)}")
            self.close()
            raise

    def _login_to_ai_service(self):
        """Открытие страницы AI сервиса"""
        try:
            self.page.goto(self.ai_service_url)
            # Ждем пока пользователь залогинится через Google
            self.page.wait_for_selector('.logged-in-indicator', timeout=300000)
        except Exception as e:
            self.logger.error(f"Login failed: {str(e)}")
            raise

    def analyze_repository(self, repo_url):
        """Анализ репозитория"""
        try:
            # Получаем код из GitHub
            code_files = self._get_repository_contents(repo_url)
            
            # Формируем промпт для анализа
            prompt = self._prepare_analysis_prompt(code_files)
            
            # Отправляем в AI сервис
            textarea = self.page.locator("textarea")
            textarea.fill(prompt)
            textarea.press("Enter")
            
            # Ждем и получаем ответ
            response = self.page.wait_for_selector('.assistant-message')
            return {
                "status": "success",
                "results": response.text_content()
            }
            
        except Exception as e:
            self.logger.error(f"Analysis failed: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }

    def _get_repository_contents(self, repo_url):
        """Получение содержимого репозитория"""
        try:
            path = urlparse(repo_url).path.strip('/')
            owner, repo = path.split('/')[-2:]
            
            g = Github()  # Анонимный доступ для публичных репозиториев
            repo = g.get_repo(f"{owner}/{repo}")
            
            contents = []
            items = repo.get_contents("")
            
            while items:
                file_content = items.pop(0)
                if file_content.type == "dir":
                    items.extend(repo.get_contents(file_content.path))
                elif self._is_code_file(file_content.path):
                    try:
                        content = base64.b64decode(file_content.content).decode()
                        contents.append({
                            'path': file_content.path,
                            'content': content
                        })
                    except Exception as e:
                        self.logger.error(f"Error decoding {file_content.path}: {str(e)}")
            
            return contents
            
        except Exception as e:
            raise Exception(f"Failed to load repository: {str(e)}")

    def _is_code_file(self, file_path):
        """Проверка является ли файл кодом"""
        code_extensions = {'.py', '.js', '.java', '.cpp', '.h', '.cs', '.php', '.rb'}
        return any(file_path.endswith(ext) for ext in code_extensions)

    def _prepare_analysis_prompt(self, code_files):
        """Подготовка промпта для анализа"""
        prompt = """Please analyze this code and provide:
1. Potential bugs and errors
2. Compatibility issues between files
3. Incomplete or missing code
4. Security concerns
5. Optimization suggestions

Code files:
"""
        for file in code_files:
            prompt += f"\n--- {file['path']} ---\n{file['content']}\n"
        return prompt

    def close(self):
        """Закрытие браузера"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

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
