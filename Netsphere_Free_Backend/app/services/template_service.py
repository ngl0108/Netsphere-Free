from jinja2 import Template, meta, Environment

class TemplateRenderer:
    @staticmethod
    def render(template_content: str, context: dict) -> str:
        """
        renders text with context.
        """
        try:
            env = Environment()
            template = env.from_string(template_content)
            rendered_content = template.render(**context)
            return rendered_content.strip()
        except Exception as e:
            raise ValueError(f"Error rendering template: {str(e)}")

    @staticmethod
    def get_variables(template_content: str) -> set:
        """
        Extracts undeclared variables from the template.
        """
        env = Environment()
        ast = env.parse(template_content)
        return meta.find_undeclared_variables(ast)

    @staticmethod
    def validate_context(template_content: str, context: dict) -> list:
        """
        Returns a list of missing variables.
        """
        required_vars = TemplateRenderer.get_variables(template_content)
        missing = [var for var in required_vars if var not in context and var not in ['range', 'len']] # exlucde builtins
        return missing

    @staticmethod
    def merge_variables(global_vars: dict, site_vars: dict, device_vars: dict) -> dict:
        """
        Hierarchical merge: Device > Site > Global
        """
        merged = {}
        if global_vars: merged.update(global_vars)
        if site_vars: merged.update(site_vars)
        if device_vars: merged.update(device_vars)
        return merged
