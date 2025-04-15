def init_plugin(app):
    @app.route('/hello_plugin')
    def hello_plugin():
        return 'Hello from plugin!'
