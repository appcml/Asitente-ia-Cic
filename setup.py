from setuptools import setup, find_packages

setup(
    name="bebe-ia",
    version="0.1.0",
    description="Un asistente de IA que crece desde cero como un bebé",
    author="Tu Nombre",
    packages=find_packages(),
    install_requires=[
        "torch>=2.0.0",
        "numpy>=1.24.0",
        "tqdm>=4.65.0",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "bebe-ia=bebe_ia.main:main",
        ],
    },
)
