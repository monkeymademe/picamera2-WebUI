def init_plugin(app, context=None):
    @app.route('/hello_plugin')
    def hello_plugin():
        return 'Hello from plugin!'
