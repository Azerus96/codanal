import os
import sys
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
    def __init__(self, ai_service_url="https://chat.claude.ai"):
        self.ai_service_url = ai_service_url
        self.playwright = None
        self.browser = None
        self.page = None
        self.logger = logging.getLogger(__name__)

    def start(self):
        """Инициализация браузера"""
        try:
            self.playwright = sync_playwright().start()
            
            # Настройки браузера
            browser_options = {
                'headless': True,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--disable-extensions',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
            }
            
            # Проверяем и устанавливаем путь к браузеру для Render
            if os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
                chrome_path = os.path.join(
                    os.environ['PLAYWRIGHT_BROWSERS_PATH'],
                    'chromium-1140',
                    'chrome-linux',
                    'chrome'
                )
                if os.path.exists(chrome_path):
                    browser_options['executable_path'] = chrome_path
                else:
                    self.logger.warning(f"Chrome not found at {chrome_path}, using default")

            self.browser = self.playwright.chromium.launch(**browser_options)
            self.page = self.browser.new_page()
            
            # Дополнительные настройки страницы
            self.page.set_viewport_size({"width": 1920, "height": 1080})
            self.page.set_default_timeout(60000)  # 60 секунд таймаут
            
            self._login_to_ai_service()
        except Exception as e:
            self.logger.error(f"Failed to start browser: {str(e)}")
            self.close()
            raise

    def _login_to_ai_service(self):
        """Открытие страницы AI сервиса"""
        try:
            self.logger.info(f"Navigating to {self.ai_service_url}")
            self.page.goto(self.ai_service_url, wait_until="networkidle")
            
            # Ждем появления кнопки входа через Google
            self.logger.info("Waiting for Google login button")
            self.page.wait_for_selector('button:has-text("Continue with Google")', 
                                      timeout=30000)
            
            # Ждем успешного входа
            self.logger.info("Waiting for successful login")
            self.page.wait_for_selector('.logged-in-indicator', 
                                      timeout=300000)  # 5 минут на вход
            
            self.logger.info("Successfully logged in to AI service")
        except Exception as e:
            self.logger.error(f"Login failed: {str(e)}")
            raise

    def analyze_repository(self, repo_url):
        """Анализ репозитория"""
        try:
            self.logger.info(f"Starting analysis of repository: {repo_url}")
            
            # Проверка наличия браузера на Render
            if os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
                browser_path = os.path.join(
                    os.environ['PLAYWRIGHT_BROWSERS_PATH'],
                    'chromium-1140',
                    'chrome-linux',
                    'chrome'
                )
                if not os.path.exists(browser_path):
                    raise Exception(f"Browser not found at {browser_path}")
            
            # Получаем код из GitHub
            self.logger.info("Fetching repository contents")
            code_files = self._get_repository_contents(repo_url)
            
            if not code_files:
                return {
                    "status": "error",
                    "message": "No code files found in repository"
                }
            
            # Формируем промпт для анализа
            self.logger.info("Preparing analysis prompt")
            prompt = self._prepare_analysis_prompt(code_files)
            
            # Отправляем в AI сервис
            self.logger.info("Sending code to AI service")
            textarea = self.page.locator("textarea")
            
            # Очищаем предыдущий текст, если есть
            textarea.clear()
            
            # Вводим текст порциями, чтобы избежать проблем с большими текстами
            chunk_size = 1000
            for i in range(0, len(prompt), chunk_size):
                chunk = prompt[i:i + chunk_size]
                textarea.type(chunk, delay=50)
            
            # Отправляем
            self.logger.info("Sending prompt to AI")
            textarea.press("Enter")
            
            # Ждем и получаем ответ
            self.logger.info("Waiting for AI response")
            response = self.page.wait_for_selector('.assistant-message', 
                                                 timeout=300000)  # 5 минут на ответ
            
            result = response.text_content()
            self.logger.info("Analysis completed successfully")
            
            return {
                "status": "success",
                "results": result
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
            
            self.logger.info(f"Accessing repository: {owner}/{repo}")
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
                        self.logger.info(f"Loaded file: {file_content.path}")
                    except Exception as e:
                        self.logger.error(f"Error decoding {file_content.path}: {str(e)}")
            
            self.logger.info(f"Loaded {len(contents)} code files")
            return contents
            
        except Exception as e:
            self.logger.error(f"Failed to load repository: {str(e)}")
            raise

    def _is_code_file(self, file_path):
        """Проверка является ли файл кодом"""
        code_extensions = {
            '.py', '.js', '.jsx', '.ts', '.tsx', 
            '.java', '.cpp', '.hpp', '.c', '.h',
            '.cs', '.php', '.rb', '.go', '.rs',
            '.swift', '.kt', '.kts', '.scala',
            '.html', '.css', '.scss', '.sass',
            '.vue', '.svelte', '.dart'
        }
        return any(file_path.lower().endswith(ext) for ext in code_extensions)

    def _prepare_analysis_prompt(self, code_files):
        """Подготовка промпта для анализа"""
        prompt = """Please analyze this code and provide a detailed report covering:

1. Code Quality and Structure:
   - Architecture and design patterns
   - Code organization
   - Naming conventions
   - Code duplication

2. Potential Issues:
   - Bugs and logical errors
   - Security vulnerabilities
   - Performance bottlenecks
   - Memory leaks

3. Compatibility:
   - Dependencies between files
   - Version conflicts
   - Platform-specific issues

4. Improvements:
   - Optimization suggestions
   - Best practices recommendations
   - Modern alternatives to used approaches

5. Missing Elements:
   - Incomplete implementations
   - Missing error handling
   - Required documentation
   - Test coverage

Please provide specific examples and suggestions for improvements.

Code files to analyze:
"""
        for file in code_files:
            prompt += f"\n\n=== {file['path']} ===\n{file['content']}"
        
        return prompt

    def close(self):
        """Закрытие браузера"""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            self.logger.info("Browser closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing browser: {str(e)}")

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    """Endpoint для анализа репозитория"""
    repo_url = request.form.get('repo_url')
    if not repo_url:
        return jsonify({
            "status": "error",
            "message": "Repository URL is required"
        })
    
    # Проверка формата URL
    if not repo_url.startswith('https://github.com/'):
        return jsonify({
            "status": "error",
            "message": "Invalid GitHub URL. Please provide a valid GitHub repository URL"
        })
    
    logger.info(f"Starting analysis for repository: {repo_url}")
    
    try:
        analyzer = CodeAnalyzer()
        analyzer.start()
        
        try:
            results = analyzer.analyze_repository(repo_url)
            logger.info("Analysis completed successfully")
            return jsonify(results)
        finally:
            analyzer.close()
            
    except Exception as e:
        error_message = str(e)
        logger.error(f"Analysis failed: {error_message}")
        return jsonify({
            "status": "error",
            "message": f"Analysis failed: {error_message}"
        })

@app.errorhandler(Exception)
def handle_error(error):
    """Глобальный обработчик ошибок"""
    logger.error(f"Unhandled error: {str(error)}")
    return jsonify({
        "status": "error",
        "message": "An unexpected error occurred. Please try again later."
    }), 500

@app.route('/health')
def health_check():
    """Endpoint для проверки работоспособности"""
    return jsonify({
        "status": "healthy",
        "version": "1.0.0"
    })

if __name__ == '__main__':
    # Настройка порта для Render
    port = int(os.environ.get('PORT', 5000))
    
    # Дополнительные настройки для production
    if os.environ.get('RENDER'):
        debug = False
        host = '0.0.0.0'
    else:
        debug = True
        host = 'localhost'
    
    logger.info(f"Starting application on {host}:{port}")
    app.run(host=host, port=port, debug=debug)
