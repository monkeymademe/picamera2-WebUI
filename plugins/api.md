# CamUI Plugin API

## Plugin Initialization

Each plugin must define an `init_plugin(app)` function, which will be called with the Flask app instance. Plugins can use this to register routes, hooks, or perform other setup.

```python
def init_plugin(app):
    # Register routes, hooks, etc.
    pass
```

## Hooks

Hooks allow plugins to react to certain events in the main application. To register a hook, append your callback to the appropriate hook list.

### Available Hooks

#### after_image_capture
- **Description:** Called after a still image is captured by any camera.
- **Signature:**
  ```python
  def after_image_capture(camera_num, image_path):
      # camera_num: int - The camera number
      # image_path: str - The path to the saved image
      pass
  ```
- **How to register:**
  ```python
  plugin_hooks['after_image_capture'].append(after_image_capture)
  ``` 