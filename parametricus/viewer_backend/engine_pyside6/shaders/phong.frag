#version 330 core

struct Light
{
    vec3 direction;
    vec3 color;
};

struct Material
{
    vec3 color;
    float ambient;
    float specular;
    float shininess;
};

uniform Light light;
uniform Material material;
uniform vec3 viewPos;

in vec3 FragPos;
in vec3 Normal;

out vec4 FragColor;

void main()
{
    vec3 N = normalize(Normal);

    vec3 L = normalize(-light.direction);

    float diff = max(dot(N,L),0.0);

    vec3 diffuse =
        diff *
        material.color *
        light.color;

    vec3 ambient =
        material.ambient *
        material.color;

    vec3 V =
        normalize(viewPos-FragPos);

    vec3 R =
        reflect(-L,N);

    float spec =
        pow(
            max(dot(V,R),0.0),
            material.shininess
        );

    vec3 specular =
        material.specular *
        spec *
        light.color;

    FragColor =
        vec4(
            ambient +
            diffuse +
            specular,
            1.0
        );
}
