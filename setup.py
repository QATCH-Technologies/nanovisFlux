from setuptools import find_packages, setup

setup(
    name="nanovisFlux",
    version="1.0.0",
    author="QATCH Technologies",
    description="Automation and operation trunk for QATCH Technologies nanovisFlux.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/QATCH-Technologies/nanovisFlux.git",
    packages=find_packages(),
    python_requires=">=3.11.7",
    install_requires=[
        "pyserial==3.5",
        "pyserial-asyncio==0.6",
        "websockets==12.0",
        "aiohttp==3.9.1",
        "opentrons==7.0.2",
        "opentrons-shared-data==7.0.2",
        "pydantic==1.10.26",
        "python-dotenv==1.0.0",
        "loguru==0.7.2",
        "numpy==2.0.2",
        "tqdm==4.67.1",
    ],
    extras_require={
        "ml": [
            "ultralytics==8.3.252",
            "scikit-learn==1.7.2",
            "scipy==1.16.2",
            "torch==2.8.0",
            "torchaudio==2.8.0",
            "torchvision==0.23.0",
        ],
        "test": [
            "pytest==7.4.3",
            "pytest-asyncio==0.23.2",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Topic :: Scientific/Engineering",
    ],
)