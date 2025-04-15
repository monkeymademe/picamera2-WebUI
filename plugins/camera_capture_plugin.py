from flask import render_template_string, request, jsonify

def init_plugin(app, context):
    cameras = context['cameras']
    plugin_hooks = context['plugin_hooks']

    # Register a simple after_image_capture hook
    def log_capture(camera_num, image_path):
        print(f"[Plugin] Camera {camera_num} captured image: {image_path}")
    plugin_hooks['after_image_capture'].append(log_capture)

    # Route to display capture buttons for each camera
    @app.route('/plugin_capture', methods=['GET'])
    def plugin_capture():
        camera_list = list(cameras.keys())
        return render_template_string('''
            <h2>Plugin Camera Capture</h2>
            {% for cam_num in camera_list %}
                <div>
                    <button onclick="capture({{ cam_num }})">Capture Still for Camera {{ cam_num }}</button>
                </div>
            {% endfor %}
            <script>
            function capture(cam_num) {
                fetch(`/capture_still_${cam_num}`, {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    alert('Camera ' + cam_num + ': ' + (data.success ? 'Captured!' : 'Failed: ' + data.message));
                });
            }
            </script>
        ''', camera_list=camera_list) 