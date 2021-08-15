"""Setup module installation."""

from setuptools import find_packages, setup

if __name__ == "__main__":
    MODULE_NAME = "simplebot_feeds"
    DESC = "Subscribe to RSS/Atoms feeds in Delta Chat (SimpleBot plugin)"
    KEYWORDS = "simplebot plugin deltachat feeds rss atom"

    with open("README.rst") as fh:
        long_description = fh.read()

    setup(
        name=MODULE_NAME,
        setup_requires=["setuptools_scm"],
        use_scm_version={
            "root": ".",
            "relative_to": __file__,
            "tag_regex": r"^(?P<prefix>v)?(?P<version>[^\+]+)(?P<suffix>.*)?$",
            "git_describe_command": "git describe --dirty --tags --long --match v*.*.*",
        },
        description=DESC,
        long_description=long_description,
        long_description_content_type="text/x-rst",
        author="The SimpleBot Contributors",
        author_email="adbenitez@nauta.cu",
        url=f"https://github.com/simplebot-org/{MODULE_NAME}",
        keywords=KEYWORDS,
        license="MPL",
        classifiers=[
            "Development Status :: 3 - Alpha",
            "Environment :: Plugins",
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
            "Operating System :: OS Independent",
            "Topic :: Utilities",
        ],
        zip_safe=False,
        include_package_data=True,
        packages=find_packages(),
        install_requires=["simplebot", "feedparser", "requests", "html2text"],
        entry_points={
            "simplebot.plugins": "{0} = {0}".format(MODULE_NAME),
        },
    )
