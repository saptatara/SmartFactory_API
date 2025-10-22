import requests
import json
from urllib.parse import urljoin

class IoTDeviceTester:
    def __init__(self):
        self.base_url = "http://13.204.181.110/"
        self.device_id = 1
        self.write_token = "9e35eb16-e8e3-41e1-bb6a-121add53b6f0"
        
    def test_connection(self):
        """Test the basic connection to the server"""
        try:
            response = requests.get(self.base_url, timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
            
    def test_authentication(self):
        """Test authentication with different token formats"""
        tests = [
            {
                'name': 'Raw token (your current approach)',
                'headers': {
                    'Authorization': self.write_token,
                    'Content-Type': 'application/json'
                }
            },
            {
                'name': 'Token prefix (correct approach)',
                'headers': {
                    'Authorization': f'Token {self.write_token}',
                    'Content-Type': 'application/json'
                }
            },
            {
                'name': 'Bearer prefix (alternative)',
                'headers': {
                    'Authorization': f'Bearer {self.write_token}',
                    'Content-Type': 'application/json'
                }
            }
        ]
        
        results = []
        url = urljoin(self.base_url, f"/api/write_data/{self.device_id}/")
        data = {'T1_In': 25.5}
        
        for test in tests:
            try:
                response = requests.post(
                    url, 
                    headers=test['headers'], 
                    json=data,
                    timeout=5
                )
                results.append({
                    'name': test['name'],
                    'status_code': response.status_code,
                    'response': response.text
                })
            except requests.exceptions.RequestException as e:
                results.append({
                    'name': test['name'],
                    'status_code': 'Error',
                    'response': str(e)
                })
                
        return results

def create_troubleshooting_ui():
    """Create a PyGame UI for troubleshooting the IoT device connection"""
    import pygame
    import sys
    
    pygame.init()
    width, height = 800, 600
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("IoT Device Connection Troubleshooter")
    
    # Colors
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    GREEN = (0, 200, 0)
    RED = (200, 0, 0)
    BLUE = (0, 120, 255)
    LIGHT_GRAY = (220, 220, 220)
    DARK_GRAY = (180, 180, 180)
    
    # Fonts
    title_font = pygame.font.SysFont('Arial', 28, bold=True)
    header_font = pygame.font.SysFont('Arial', 22, bold=True)
    normal_font = pygame.font.SysFont('Arial', 18)
    small_font = pygame.font.SysFont('Arial', 16)
    
    tester = IoTDeviceTester()
    connection_status = tester.test_connection()
    auth_results = tester.test_authentication()
    
    # Button
    retry_button = pygame.Rect(width//2 - 75, height - 80, 150, 50)
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                if retry_button.collidepoint(event.pos):
                    connection_status = tester.test_connection()
                    auth_results = tester.test_authentication()
        
        screen.fill(WHITE)
        
        # Title
        title = title_font.render("IoT Device Connection Troubleshooter", True, BLUE)
        screen.blit(title, (width//2 - title.get_width()//2, 20))
        
        # Server status
        y_pos = 70
        status_text = "Server Connection: "
        status_text += "SUCCESS" if connection_status else "FAILED"
        status_color = GREEN if connection_status else RED
        status_surface = header_font.render(status_text, True, status_color)
        screen.blit(status_surface, (50, y_pos))
        
        # URL information
        y_pos += 40
        url_text = f"Base URL: {tester.base_url}"
        screen.blit(normal_font.render(url_text, True, BLACK), (50, y_pos))
        
        y_pos += 30
        device_text = f"Device ID: {tester.device_id}"
        screen.blit(normal_font.render(device_text, True, BLACK), (50, y_pos))
        
        y_pos += 30
        token_text = f"Write Token: {tester.write_token}"
        screen.blit(small_font.render(token_text, True, DARK_GRAY), (50, y_pos))
        
        # Authentication test results
        y_pos += 50
        auth_title = header_font.render("Authentication Test Results:", True, BLUE)
        screen.blit(auth_title, (50, y_pos))
        
        y_pos += 40
        for i, result in enumerate(auth_results):
            # Test name
            name_text = f"{i+1}. {result['name']}"
            screen.blit(normal_font.render(name_text, True, BLACK), (70, y_pos))
            
            # Status code
            status_text = f"Status: {result['status_code']}"
            status_color = GREEN if result['status_code'] == 200 else RED
            screen.blit(normal_font.render(status_text, True, status_color), (400, y_pos))
            
            # Response
            y_pos += 30
            response_text = f"Response: {result['response'][:60]}..."
            screen.blit(small_font.render(response_text, True, DARK_GRAY), (90, y_pos))
            
            y_pos += 40
        
        # Recommendations
        y_pos += 20
        rec_title = header_font.render("Recommendations:", True, BLUE)
        screen.blit(rec_title, (50, y_pos))
        
        y_pos += 40
        recommendations = [
            "1. Use 'Token <your_token>' format in Authorization header",
            "2. Verify the device ID matches your device in Django Admin",
            "3. Check that the token has write_data permission",
            "4. Ensure the device is associated with the correct customer",
            "5. Verify the API endpoint URL is correct"
        ]
        
        for rec in recommendations:
            screen.blit(normal_font.render(rec, True, BLACK), (70, y_pos))
            y_pos += 30
        
        # Retry button
        pygame.draw.rect(screen, BLUE, retry_button, border_radius=10)
        retry_text = normal_font.render("Retry Tests", True, WHITE)
        screen.blit(retry_text, (retry_button.x + retry_button.width//2 - retry_text.get_width()//2, 
                                retry_button.y + retry_button.height//2 - retry_text.get_height()//2))
        
        pygame.display.flip()
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    create_troubleshooting_ui()
